"""FastAPI backend for the edge AI terminal.

M2 scope: persistent serial service and device endpoints.
LLM/VLM endpoints are added in M3/M5.
"""
import base64
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .knowledge import build_messages, kb
from .serial_service import SerialService
from .tool_router import route_tool

APP_VERSION = "0.7.4"
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


def _load_remote_access():
    """Optional Basic-auth credentials for Cloudflare tunnel requests.

    The file is kept outside the repository, one line: user:password.
    LAN requests (no Cloudflare headers) remain password-free.
    """
    path = Path(os.environ.get("AI_ACCESS_FILE", str(Path.home() / ".ai_terminal_access")))
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" in line:
                user, password = line.split(":", 1)
                if user.strip() and password.strip():
                    return user.strip(), password.strip()
    except Exception:
        return None
    return None


REMOTE_ACCESS = _load_remote_access()


@app.middleware("http")
async def remote_auth(request: Request, call_next):
    if REMOTE_ACCESS and (
        request.headers.get("cf-connecting-ip") or request.headers.get("cf-ray")
    ):
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                raw = base64.b64decode(header.split(None, 1)[1]).decode("utf-8")
                user, _, password = raw.partition(":")
                ok = (
                    secrets.compare_digest(user, REMOTE_ACCESS[0])
                    and secrets.compare_digest(password, REMOTE_ACCESS[1])
                )
            except Exception:
                ok = False
        if not ok:
            return Response(
                "需要访问密码",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="CT117E-M4 AI"'},
            )
    return await call_next(request)


@app.get("/api/whoami")
def whoami(request: Request) -> dict:
    return {
        "client": request.client.host if request.client else None,
        "cf_connecting_ip": request.headers.get("cf-connecting-ip"),
        "cf_ray": request.headers.get("cf-ray"),
        "remote_auth": bool(REMOTE_ACCESS),
    }


@app.on_event("startup")
def startup_load_knowledge() -> None:
    # 1608 chunks tokenise in about a second on the Pi; keep startup
    # deterministic so the first question already has retrieval available.
    kb.load()


class LedRequest(BaseModel):
    id: int = Field(ge=1, le=8)
    on: bool


class LedAllRequest(BaseModel):
    mask: int = Field(ge=0, le=255)


class LcdRequest(BaseModel):
    line: int = Field(ge=0, le=9)
    text: str = Field(min_length=0, max_length=32)


class PwmRequest(BaseModel):
    ch: int = Field(ge=1, le=2)
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


def _led_state(response: str) -> dict:
    mask = None
    parts = response.split()
    if len(parts) >= 3 and parts[0] == "OK" and parts[1] in ("LED", "LEDALL"):
        try:
            mask = int(parts[2], 16)
        except ValueError:
            mask = None
    return {
        "ok": mask is not None,
        "response": response,
        "mask": mask,
        "states": {str(i): bool(mask & (1 << (i - 1))) for i in range(1, 9)} if mask is not None else {},
    }


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
            "/api/device/leds",
            "/api/device/ledall",
            "/api/device/lcd",
            "/api/device/lcd/clear",
            "/api/device/adc",
            "/api/device/adc?ch=2",
            "/api/device/pwm",
            "/api/device/pwm2",
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
def device_adc(ch: int = 1) -> dict:
    if ch not in (1, 2):
        raise HTTPException(status_code=400, detail="ch must be 1 or 2")
    command = "ADC?" if ch == 1 else "ADC2?"
    response = _send(command, wait=0.8)
    raw = None
    if response.startswith("OK ADC"):
        try:
            raw = int(response.split()[2])
        except (IndexError, ValueError):
            raw = None
    voltage = round(raw * 3.3 / 4095.0, 3) if raw is not None else None
    mv = round(raw * 3300.0 / 4095.0) if raw is not None else None
    return {
        "ok": raw is not None,
        "response": response,
        "ch": ch,
        "raw": raw,
        "voltage": voltage,
        "mv": mv,
        "pin": "PB12 / ADC1_IN11" if ch == 1 else "PB15 / ADC2_IN15",
        "resolution": 12,
    }


@app.get("/api/device/leds")
def device_leds() -> dict:
    return _led_state(_send("LED?", wait=0.8))


@app.post("/api/device/led")
def device_led(req: LedRequest) -> dict:
    response = _send(f"LED {req.id} {1 if req.on else 0}", wait=0.5)
    result = _led_state(_send("LED?", wait=0.5)) if response.startswith("OK LED") else _led_state(response)
    result["ok"] = response.startswith("OK LED")
    result["response"] = response
    return result


@app.post("/api/device/ledall")
def device_ledall(req: LedAllRequest) -> dict:
    response = _send(f"LEDALL {req.mask:02X}", wait=0.8)
    result = _led_state(response)
    result["ok"] = response.startswith("OK LEDALL")
    return result


@app.post("/api/device/lcd")
def device_lcd(req: LcdRequest) -> dict:
    text = req.text.replace("\n", " ").replace("\r", " ")
    response = _send(f"LCD {req.line} {text}", wait=1.0)
    return {"ok": response.startswith("OK LCD"), "response": response}


@app.post("/api/device/lcd/clear")
def device_lcd_clear() -> dict:
    response = _send("LCDCLR", wait=1.5)
    return {"ok": response.startswith("OK LCDCLR"), "response": response}


@app.get("/api/device/pwm")
def device_pwm_status() -> dict:
    response = _send("PWM?", wait=0.8)
    duty = None
    if response.startswith("OK PWM "):
        try:
            duty = int(response.split()[3])
        except (IndexError, ValueError):
            duty = None
    return {
        "ok": duty is not None,
        "response": response,
        "ch": 1,
        "duty": duty,
        "frequency_hz": 1000,
        "pin": "PA2 / TIM15_CH1",
    }


@app.get("/api/device/pwm2")
def device_pwm2_status() -> dict:
    response = _send("PWM2?", wait=0.8)
    duty = None
    if response.startswith("OK PWM 2 "):
        try:
            duty = int(response.split()[3])
        except (IndexError, ValueError):
            duty = None
    return {
        "ok": duty is not None,
        "response": response,
        "ch": 2,
        "duty": duty,
        "frequency_hz": 1000,
        "pin": "PA3 / TIM15_CH2",
    }


@app.post("/api/device/pwm")
def device_pwm(req: PwmRequest) -> dict:
    response = _send(f"PWM {req.ch} {req.duty}", wait=0.5)
    return {
        "ok": response.startswith("OK PWM"),
        "response": response,
        "ch": req.ch,
        "duty": req.duty,
        "frequency_hz": 1000,
        "pin": "PA2 / TIM15_CH1" if req.ch == 1 else "PA3 / TIM15_CH2",
    }


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

    # Date/time is system state, not a knowledge-base answer.  Answer it
    # exactly from the Pi clock instead of asking the 0.5B model to guess.
    if re.search(r"今天(是)?几号|今天(是)?什么日期|现在(是)?什么日期|今天星期几|现在几点|当前时间", last) \
            and not re.search(r"rtc|板卡|开发板|stm32|lcd|代码|程序|怎么|如何|配置", last, re.I):
        now = datetime.now()
        weekdays = "一二三四五六日"
        time_text = (
            f"今天是 {now.year} 年 {now.month} 月 {now.day} 日，"
            f"星期{weekdays[now.weekday()]}；当前时间 {now:%H:%M}（树莓派系统时间）。"
        )

        async def time_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "time"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": time_text}}], "mode": "time"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(time_stream(), media_type="text/event-stream")

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
        meta_re = re.compile(
            r"你是谁|你叫什么|你的名字|自我介绍|介绍一下你自己|你是什么模型|你是哪个模型|"
            r"你用的什么模型|你能做什么|你会什么|你有什么功能|who are you|what can you do",
            re.I,
        )
        greeting_re = re.compile(r"^\s*(你好|您好|hi|hello|嗨|在吗|谢谢|感谢|多谢)[！!。,.?\s]*$", re.I)

        async def fixed_stream(text: str, mode: str):
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": mode},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": text}}], "mode": mode},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        if meta_re.search(last):
            meta_text = (
                "我是**蓝桥杯嵌入式 AI 助教**，运行在树莓派 4B 上。\n\n"
                "- 底层语言模型：**Qwen2.5-0.5B-Instruct（GGUF Q4_K_M）**，本地推理，不依赖云端 API。\n"
                f"- 知识库：**CT117E-M4 专用知识库**，当前 {len(kb.docs)} 个片段 / {len({d.get('source') for d in kb.docs})} 个来源，覆盖板卡、外设、代码与真题。\n"
                "- 我还能通过规则路由控制板载 LED、LCD、ADC、PWM（例如“让 LED1 亮起来”）。\n\n"
                "你可以直接问：“LED 怎么点亮？”“USART1 怎么配置？”“I2C 读写 AT24C02 怎么写？”"
            )
            return StreamingResponse(fixed_stream(meta_text, "meta"), media_type="text/event-stream")

        if greeting_re.search(last):
            greet_text = (
                "你好！我是蓝桥杯嵌入式 AI 助教，专精 CT117E-M4 / STM32G431RBT6。"
                "可以问我板卡、外设、代码和历年真题，也可以直接说“让 LED1 亮起来”。"
            )
            return StreamingResponse(fixed_stream(greet_text, "greeting"), media_type="text/event-stream")

        # 其余问题（包括天气、通用“代码是什么”等）交给本地 Qwen；
        # 提示词要求它不要编造实时数据和本板具体引脚。

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
