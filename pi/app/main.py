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
from typing import List, Optional

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

APP_VERSION = "0.9.8"
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



def _history_answer(text: str, messages) -> Optional[str]:
    """Answer explicit meta-memory questions from the real chat history."""
    t = (text or "").strip()
    prior = list(messages[:-1])
    if re.search(r"记住|数字", t) and re.search(r"多少|什么|几", t):
        for m in reversed(prior):
            # Only the user's own words count: board answers contain numbers
            # such as G431/PC8 that must not overwrite the remembered value.
            if m.role != "user":
                continue
            nums = re.findall(r"(?<![A-Za-z0-9])[0-9]{3,8}(?![A-Za-z0-9])", m.content or "")
            if nums:
                return f"你让我记住的数字是 **{nums[-1]}**。"
    if re.search(r"我刚才(问|说)了什么|上一个问题|上一句", t):
        for m in reversed(prior):
            if m.role == "user" and m.content:
                return f"你刚才问的是：**{m.content[:200]}**"
    return None


def _definition_term(text: str) -> str:
    """Extract X from “什么是 X / X 是什么 / 什么叫 X / 解释 X”."""
    t = (text or "").strip()
    m = re.match(
        r"^(?:什么是|啥是|什么叫|何谓|解释一下|解释下|解释|介绍一下|介绍|简述|说说|讲讲)\s*(.+?)\s*[？?]?$",
        t,
    )
    if m:
        return m.group(1).strip()
    m = re.match(r"^(.+?)\s*(?:是什么|指什么|是什么意思|的含义|的定义)\s*[？?]?$", t)
    return m.group(1).strip() if m else ""


def _clean_model_text(text: str, has_sources: bool) -> str:
    """Remove citation noise, prompt leakage and repeated text from the 0.5B.

    The small model sometimes loops on the same sentence or invents [1][2]
    references when no retrieval context was supplied.  Cleanup happens after
    generation, so the SSE response is sent as one corrected block.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if not has_sources:
        text = re.sub(r"[ \t]*\[\d+\](?:[ \t]*\[\d+\])*", "", text)
        text = re.sub(
            r"^\s*(?:结论|步骤/代码要点|步骤|代码要点|易错点|原理解释)\s*[：:]\s*",
            "",
            text,
            flags=re.M,
        )
    # Strip fragments of the system prompt that the model occasionally echoes.
    text = re.sub(
        r"\[[^\]]*(?:300\s*字以内|Markdown|不要编造|检索资料|回答要求)[^\]]*\]",
        "",
        text,
    )
    text = re.sub(
        r"^\s*(?:结论/步骤|结论|步骤|易错点)\s*[：:]\s*$",
        "",
        text,
        flags=re.M,
    )
    leak_re = re.compile(r"300\s*字以内|代码用\s*Markdown|不要编造|只回答|回答要求")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    kept = []
    seen_paragraphs = set()
    seen_sentences = set()
    for para in paragraphs:
        key = re.sub(r"\s+", "", para)
        if not key or key in seen_paragraphs:
            continue
        seen_paragraphs.add(key)
        sentences = re.split(r"(?<=[。！？!?；;])", para)
        cleaned = []
        for sentence in sentences:
            norm = re.sub(r"\s+", "", sentence)
            if not norm or leak_re.search(sentence):
                continue
            # Drop a sentence that already appeared anywhere in the answer.
            if norm in seen_sentences:
                continue
            seen_sentences.add(norm)
            cleaned.append(sentence)
        merged = "".join(cleaned).strip()
        if merged:
            kept.append(merged)
    answer = "\n\n".join(kept).strip()
    # Do not end on a half-generated sentence.
    if answer and "```" not in answer and len(answer) > 180:
        if answer[-1] not in "。！？!?；;：:`）)】”\"":
            cut = max(answer.rfind(x) for x in "。！？!?；;")
            if cut >= 80:
                answer = answer[:cut + 1].strip()
    return answer

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
    fast_only: bool = False


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

    # Weather is a hard boundary: no live data, answer deterministically.
    if re.search(r"天气|气温|下雨|下雪|降雨|台风|空气质量", last) and not re.search(
        r"rtc|板卡|开发板|stm32|传感器|lcd|代码|程序|配置", last, re.I
    ):
        weather_text = "我无法获取实时天气，请查看手机天气或天气网站。"

        async def weather_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "weather"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": weather_text}}], "mode": "weather"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(weather_stream(), media_type="text/event-stream")

    # Explicit “remember this number” instruction: acknowledge it directly so
    # the board retriever does not answer with an unrelated G431/PC8 number.
    remember = re.search(r"(?:记住|记一下)[^0-9]{0,12}([0-9]{3,8})", last)
    if remember and not re.search(r"多少|什么|几|哪个", last):
        remember_text = f"好的，我记住了：**{remember.group(1)}**。"

        async def remember_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "memory"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": remember_text}}], "mode": "memory"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(remember_stream(), media_type="text/event-stream")

    memory_text = _history_answer(last, req.messages)
    if memory_text:
        async def memory_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "memory"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": memory_text}}], "mode": "memory"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(memory_stream(), media_type="text/event-stream")

    # A short follow-up such as "那代码呢" needs the previous question for
    # retrieval, while the LLM still sees the normal chat history.
    user_msgs = [m.content for m in req.messages if m.role == "user" and m.content]
    context_query_re = re.compile(r"记住|刚才|刚刚|上面|前面|之前|只回答|数字是多少|哪个数字|我说过|我说")
    general_def_re = re.compile(r"^(代码|程序)(是|指)?什么[？?]?$|^什么是(代码|程序)[？?]?$|^代码的含义")
    # Generic definition routes: the glossary answers common terms; board
    # terms (e.g. USART1) still fall through to fast_answer.  Unknown terms
    # get an honest "not covered" reply instead of 0.5B hallucination.
    def_term = _definition_term(last)
    compare_re = re.compile(
        r"^(.+?)(?:和|与|跟)(.+?)(?:有什么区别|有何区别|的区别是什么|的区别|有什么不同|的不同)[？?]?$"
    )
    definition_text = kb.faq_answer(last)
    compare = compare_re.match(last.strip())
    if not definition_text and compare:
        left, right = compare.group(1).strip(), compare.group(2).strip()
        left_def, right_def = kb.lookup_term(left), kb.lookup_term(right)
        if left_def and right_def:
            definition_text = f"**{left}**：{left_def}\n\n**{right}**：{right_def}"
    if not definition_text and def_term:
        definition_text = kb.lookup_term(def_term) or kb.faq_answer(last)
    if definition_text:
        async def concept_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "concept"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": definition_text}}], "mode": "concept"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(concept_stream(), media_type="text/event-stream")
    module_hint_re = re.compile(
        r"led|灯|key|按键|lcd|液晶|usart|串口|i2c|iic|24c02|adc|pwm|占空比|rtc|tim|定时器",
        re.I,
    )
    retrieval_query = last
    if not (context_query_re.search(last) or general_def_re.search(last) or def_term):
        if len(last) < 16 and len(user_msgs) >= 2:
            retrieval_query = user_msgs[-2] + " " + last

    # Explicit module in the current question wins for the code example;
    # "那代码呢" falls back to the previous module.
    code_focus = last
    if not module_hint_re.search(last) and len(user_msgs) >= 2:
        code_focus = user_msgs[-2] + " " + last

    # Retrieval-first: board/code questions are answered extractively in
    # milliseconds; only open-ended questions pay the 0.5B prompt cost.
    if (
        req.use_knowledge
        and not context_query_re.search(last)
        and not general_def_re.search(last)
    ):
        fast = await run_in_threadpool(kb.fast_answer, retrieval_query, 8, code_focus)
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

    if req.fast_only:
        async def no_fast_stream():
            yield "data: " + json.dumps(
                {"sources": [], "knowledge": {"hits": 0, "chunks": len(kb.docs)}, "mode": "no_fast"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": "NO_FAST"}}], "mode": "no_fast"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(no_fast_stream(), media_type="text/event-stream")

    # Unknown definitions continue to the local model: the assistant should
    # attempt every question, with cleanup preventing repetition/hallucinated
    # citations.  Known terms still use the fast deterministic glossary.
    context, sources = ("", [])
    if (
        req.use_knowledge
        and not (context_query_re.search(last) or general_def_re.search(last) or def_term)
        and kb.should_retrieve(retrieval_query)
    ):
        context, sources = await run_in_threadpool(
            kb.build_context, retrieval_query, 3, 700
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
                "- 底层语言模型：**Qwen2.5-1.5B-Instruct（GGUF Q4_K_M）**，本地推理，不依赖云端 API。\n"
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

    llm_history = [m.model_dump() for m in req.messages]
    # Definition/weather questions are standalone: feeding prior board history
    # makes the 0.5B model copy unrelated code or mix topics.
    if general_def_re.search(last) or def_term or re.search(r"天气|气温|下雨|下雪|新闻|股价", last):
        llm_history = []
    messages = build_messages(
        llm_history, last, context, sources,
        style="definition" if def_term else "",
    )
    # Board facts are answered deterministically; the LLM only handles open
    # questions.  160 tokens truncated explanations mid-sentence, so give the
    # 1.5B room for a complete definition (about 100–130s on the Pi).
    llm_max_tokens = min(max(req.max_tokens, 320), 512)
    payload = {
        "model": "qwen",
        "messages": messages,
        "stream": True,
        "max_tokens": llm_max_tokens,
        "temperature": req.temperature,
        # The 0.5B model tends to repeat the same sentence when uncertain.
        "repeat_penalty": 1.15,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
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
            pieces = []
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
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                        if delta:
                            pieces.append(delta)
            answer = _clean_model_text("".join(pieces), bool(sources))
            if not answer:
                answer = "本地模型没有生成有效回答，请换个问法再试。"
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": answer}}], "mode": "rag" if context else "llm"},
                ensure_ascii=False,
            ) + "\n\n"
            yield "data: [DONE]\n\n"
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
            yield "data: [DONE]\n\n"

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
