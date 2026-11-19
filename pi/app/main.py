"""FastAPI backend for the edge AI terminal.

M2 scope: persistent serial service and device endpoints.
LLM/VLM endpoints are added in M3/M5.
"""
import base64
import json
import re
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .knowledge import build_messages, kb
from .serial_service import SerialService
from .tool_router import route_tool

APP_VERSION = "0.6.0"
LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
VLM_URL = "http://127.0.0.1:8081/v1/chat/completions"

app = FastAPI(title="Lanqiao Cup Embedded AI Assistant", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

serial_svc = SerialService()


@app.on_event("startup")
def startup_load_knowledge() -> None:
    # 1606 chunks tokenise in about a second on the Pi; keep startup
    # deterministic so the first question already has retrieval available.
    kb.load()


class LedRequest(BaseModel):
    id: int = Field(ge=1, le=8)
    on: bool


class LcdRequest(BaseModel):
    line: int = Field(ge=0, le=9)
    text: str = Field(min_length=0, max_length=32)


class PwmRequest(BaseModel):
    ch: int = Field(ge=1, le=1)
    duty: int = Field(ge=0, le=100)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    max_tokens: int = Field(default=192, ge=16, le=1024)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    use_knowledge: bool = True


def _send(command: str, wait: float = 0.8) -> str:
    try:
        return serial_svc.command(command, wait=wait)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/info")
def root() -> dict:
    return {
        "name": "蓝桥杯嵌入式 AI 助教（CT117E-M4）",
        "version": APP_VERSION,
        "serial": serial_svc.status(),
        "knowledge": kb.status(),
        "endpoints": [
            "/api/device/ping",
            "/api/device/status",
            "/api/device/led",
            "/api/device/lcd",
            "/api/device/lcd/clear",
            "/api/device/adc",
            "/api/device/pwm",
            "/api/knowledge/status",
            "/api/knowledge/search?q=LED",
        ],
    }


@app.get("/api/knowledge/status")
def knowledge_status() -> dict:
    return kb.status()


@app.get("/api/knowledge/search")
def knowledge_search(q: str, top_k: int = 4) -> dict:
    top_k = max(1, min(top_k, 8))
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    hits = kb.search(q, top_k=top_k)
    return {
        "query": q,
        "count": len(hits),
        "results": [
            {
                "id": h.get("id"),
                "title": h.get("title"),
                "label": h.get("label"),
                "kind": h.get("kind"),
                "category": h.get("category"),
                "source": h.get("source"),
                "score": h.get("score"),
                "snippet": h.get("snippet"),
            }
            for h in hits
        ],
    }


@app.post("/api/knowledge/reload")
def knowledge_reload() -> dict:
    ok = kb.load(force=True)
    return {"ok": ok, **kb.status()}


@app.get("/api/device/status")
def device_status() -> dict:
    return serial_svc.status()


@app.post("/api/device/reconnect")
def device_reconnect() -> dict:
    ok = serial_svc.reconnect()
    return {"ok": ok, **serial_svc.status()}


@app.get("/api/device/ping")
def device_ping() -> dict:
    return {"ok": True, "response": _send("PING", wait=1.0)}


@app.get("/api/device/adc")
def device_adc() -> dict:
    response = _send("ADC?", wait=0.8)
    raw = None
    if response.startswith("OK ADC "):
        try:
            raw = int(response.split()[2])
        except (IndexError, ValueError):
            raw = None
    return {"ok": raw is not None, "response": response, "raw": raw}


@app.post("/api/device/led")
def device_led(req: LedRequest) -> dict:
    response = _send(f"LED {req.id} {1 if req.on else 0}", wait=0.5)
    return {"ok": response.startswith("OK LED"), "response": response}


@app.post("/api/device/lcd")
def device_lcd(req: LcdRequest) -> dict:
    text = req.text.replace("\n", " ").replace("\r", " ")
    response = _send(f"LCD {req.line} {text}", wait=1.0)
    return {"ok": response.startswith("OK LCD"), "response": response}


@app.post("/api/device/lcd/clear")
def device_lcd_clear() -> dict:
    response = _send("LCDCLR", wait=1.5)
    return {"ok": response.startswith("OK LCDCLR"), "response": response}


@app.post("/api/device/pwm")
def device_pwm(req: PwmRequest) -> dict:
    response = _send(f"PWM {req.ch} {req.duty}", wait=0.5)
    return {"ok": response.startswith("OK PWM"), "response": response}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    last = req.messages[-1].content if req.messages else ""
    tool_text = await run_in_threadpool(route_tool, last, serial_svc.command)
    if tool_text:
        async def tool_stream():
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": tool_text}}]},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(tool_stream(), media_type="text/event-stream")

    # A short follow-up such as "那代码呢" needs the previous question for
    # retrieval, while the LLM still sees the normal chat history.
    user_msgs = [m.content for m in req.messages if m.role == "user" and m.content]
    retrieval_query = last
    if len(last) < 16 and len(user_msgs) >= 2:
        retrieval_query = user_msgs[-2] + " " + last

    # Retrieval-first: board/code questions are answered extractively in
    # milliseconds; only open-ended questions pay the 0.5B prompt cost.
    if req.use_knowledge:
        fast = await run_in_threadpool(kb.fast_answer, retrieval_query)
        if fast:
            answer, used_hits = fast
            fast_sources = [kb.source_dict(h, i) for i, h in enumerate(used_hits, 1)]

            async def fast_stream():
                yield "data: " + json.dumps(
                    {
                        "sources": fast_sources,
                        "knowledge": {"hits": len(fast_sources), "chunks": len(kb.docs)},
                        "mode": "knowledge",
                    },
                    ensure_ascii=False,
                ) + "\n\n"
                yield "data: " + json.dumps(
                    {"choices": [{"delta": {"content": answer}}], "mode": "knowledge"},
                    ensure_ascii=False,
                ) + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(fast_stream(), media_type="text/event-stream")

    context, sources = ("", [])
    if req.use_knowledge:
        context, sources = await run_in_threadpool(
            kb.build_context, retrieval_query, 2, 500
        )

    if req.use_knowledge and not context:
        if re.search(r"^\s*(你好|您好|hi|hello|在吗|嗨)[！!。,.?\s]*$", last, re.I):
            scope_text = (
                "你好！我是蓝桥杯嵌入式 AI 助教，专精 CT117E-M4 / STM32G431RBT6 的板卡、外设、"
                "代码和历年真题。你可以问：LED/按键/LCD/USART/ADC/PWM/I2C/RTC 怎么配置，"
                "也可以直接说“让 LED1 亮起来”。"
            )
        else:
            scope_text = (
                "这个问题不在当前蓝桥杯板卡知识库的覆盖范围内。\n\n"
                "我主要回答 **CT117E-M4 / STM32G431RBT6** 的：\n"
                "- 引脚与硬件资源（LED、按键、LCD、ADC、PWM、I2C、USART、RTC）\n"
                "- CubeMX/Keil/HAL 配置与代码\n"
                "- 省赛/国赛真题考点与备赛路线\n\n"
                "如果你问的是树莓派、Linux 或通用大模型部署，建议查阅对应官方文档。"
            )

        async def scope_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "scope"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": scope_text}}], "mode": "scope"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(scope_stream(), media_type="text/event-stream")

    messages = build_messages(
        [m.model_dump() for m in req.messages], last, context, sources
    )
    payload = {
        "model": "qwen",
        "messages": messages,
        "stream": True,
        "max_tokens": min(req.max_tokens, 128),
        "temperature": req.temperature,
    }

    async def event_stream():
        # Sources are emitted before the first token so the UI can render
        # citations while the small model is still thinking.
        yield "data: " + json.dumps(
            {
                "sources": sources,
                "knowledge": {"hits": len(sources), "chunks": len(kb.docs)},
                "mode": "rag" if context else "llm",
            },
            ensure_ascii=False,
        ) + "\n\n"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", LLAMA_URL, json=payload) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                        yield "data: " + json.dumps(
                            {"error": f"llama-server {resp.status_code}: {body}"},
                            ensure_ascii=False,
                        ) + "\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except Exception as exc:  # noqa: BLE001
            fallback = "本地模型暂时不可用。"
            if sources:
                fallback += "\n\n先给你检索到的资料线索：\n" + "\n".join(
                    f"- **{s['label']}**：{s.get('snippet') or ''}" for s in sources
                )
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": fallback}}]},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            ) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/vision")
async def vision(
    file: UploadFile = File(...),
    prompt: str = Form("请描述这张图片")
) -> dict:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty image")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image too large (max 8MB)")

    mime = file.content_type or "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    payload = {
        "model": "smolvlm",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 128,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(VLM_URL, json=payload)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"VLM server {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"ok": True, "response": content}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"VLM request failed: {exc}") from exc


@app.get("/api/scripts")
def scripts() -> dict:
    return {
        "scripts": [
            {"id": "led_blink", "name": "LED 闪烁", "commands": ["LED 1 1", "LED 1 0"]},
            {"id": "lcd_hello", "name": "LCD 显示", "commands": ["LCDCLR", "LCD 1 Hello"]},
            {"id": "adc_read", "name": "ADC 读取", "commands": ["ADC?"]},
        ]
    }


# Serve the static frontend when built (M4). Safe to skip if absent.
_web_dir = Path(__file__).resolve().parents[2] / "web"
if (_web_dir / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
