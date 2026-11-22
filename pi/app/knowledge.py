"""BM25 knowledge retrieval for the Lanqiao Cup CT117E-M4 assistant.

The index is a JSONL file built on the PC by scripts/build_knowledge.py and
uploaded to the Pi.  Retrieval is pure Python so it runs on the Pi 4B without
extra services.  Chinese is tokenised with character bigrams plus a small
domain synonym table; ASCII identifiers (PA9, USART1, HAL_ADC_Start) are kept
as whole tokens.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
ASCII_RE = re.compile(r"[a-z0-9_+#.]{1,32}")
QUESTION_RE = re.compile(r"怎么|如何|为什么|为何|是什么|什么|原理|配置|代码|程序|步骤|教程|讲解|介绍|区别|吗|？|\?")

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "对", "把", "被", "给",
    "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "这", "那", "这个", "那个", "这些", "那些", "一个", "一种", "一些",
    "怎么", "如何", "什么", "为什么", "为何", "可以", "需要", "请问", "一下",
    "以及", "还有", "就是", "因为", "所以", "但是", "如果", "然后", "现在",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "with", "by", "from", "as", "at", "it", "this", "that",
}

# Domain synonyms: added to the query only, never to the document index.
SYNONYMS = {
    "灯": ["led"],
    "led": ["灯"],
    "串口": ["usart", "uart"],
    "usart": ["串口"],
    "uart": ["串口"],
    "液晶": ["lcd"],
    "lcd": ["液晶", "屏幕"],
    "屏幕": ["lcd"],
    "按键": ["key", "gpio"],
    "key": ["按键"],
    "模数": ["adc"],
    "adc": ["模数", "采样"],
    "占空比": ["pwm"],
    "pwm": ["占空比"],
    "定时器": ["tim"],
    "tim": ["定时器"],
    "实时时钟": ["rtc"],
    "rtc": ["实时时钟"],
    "中断": ["nvic", "exti"],
    "nvic": ["中断"],
    "时钟": ["rcc"],
    "rcc": ["时钟"],
    "引脚": ["gpio", "pin"],
    "gpio": ["引脚"],
    "eeprom": ["24c02", "i2c"],
    "24c02": ["eeprom", "i2c"],
    "iic": ["i2c"],
    "i2c": ["iic", "eeprom"],
    "at24c02": ["24c02"],
    "24c02": ["at24c02"],
    "keil": ["mdk"],
    "mdk": ["keil"],
    "cubemx": ["cube", "mx"],
    "hal": ["库"],
    "入门": ["新手", "上手", "路径"],
    "新手": ["入门", "上手", "路径"],
    "上手": ["入门", "新手", "路径"],
    "快速": ["最短", "上手"],
    "学习": ["入门", "上手", "路径"],
}

CODE_HINTS = re.compile(r"代码|例程|程序|怎么写|如何写|配置|函数|寄存器|hal|cubemx|keil|初始化|模板")
PIN_HINTS = re.compile(r"引脚|接线|原理图|pcb|pa\d|pb\d|pc\d|pd\d|pin|管脚|跳线")
EXAM_HINTS = re.compile(r"真题|题目|省赛|国赛|客观题|考点|考试|刷题|模拟题|备赛|备考|准备|比赛")
OLD_PLATFORM = "实训指导书"


def tokenize(text: str, expand: bool = False) -> List[str]:
    text = (text or "").lower()
    tokens: List[str] = []
    for run in CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            for i in range(len(run) - 1):
                tokens.append(run[i:i + 2])
            if len(run) <= 4:
                tokens.append(run)
    for word in ASCII_RE.findall(text):
        tokens.append(word)
    out = [t for t in tokens if t and t not in STOPWORDS]
    if expand:
        extra: List[str] = []
        for t in out:
            for syn in SYNONYMS.get(t, ()):
                if syn not in out and syn not in extra:
                    extra.append(syn)
        out.extend(extra)
    return out


def _short_source(row: dict) -> str:
    title = row.get("title") or ""
    source = row.get("source") or ""
    kind = row.get("kind") or ""
    meta = row.get("meta") or {}
    if kind == "board":
        section = meta.get("section") or ""
        return f"板卡事实卡 · {section}" if section else "本机实测板卡事实卡"
    if kind == "code":
        project = meta.get("project") or ""
        fname = meta.get("file") or ""
        if project and fname:
            return f"{project} / {fname}"
        return fname or title
    if kind == "ioc":
        return f"CubeMX 配置 / {meta.get('file') or title}"
    if kind == "ppt":
        return f"{title}（视频配套 PPT）"
    if kind == "xlsx":
        return f"{title}（知识点统计）"
    if kind == "docx":
        return f"{title}（真题汇编目录）"
    if kind == "exam_ocr":
        return f"{title}（真题截图 OCR）"
    page = meta.get("page")
    if page:
        return f"{title}（第 {page} 页）"
    if OLD_PLATFORM in source:
        return f"{title}（旧平台参考，注意引脚差异）"
    return title or source


def _snippet(text: str, query: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    q_tokens = [t for t in tokenize(query) if len(t) >= 2]
    pos = -1
    for t in q_tokens:
        pos = text.lower().find(t.lower())
        if pos >= 0:
            break
    if pos < 0:
        return text[:limit] + "…"
    start = max(0, pos - limit // 3)
    end = min(len(text), start + limit)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


class KnowledgeBase:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or os.environ.get(
            "KNOWLEDGE_PATH",
            str(Path(__file__).resolve().parents[2] / "knowledge" / "chunks.jsonl"),
        ))
        self.docs: List[dict] = []
        self.tf: List[Counter] = []
        self.doc_len: List[int] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0
        self.loaded = False
        self.load_error: Optional[str] = None
        self.loaded_at: Optional[float] = None
        self.manifest: dict = {}
        self._lock = threading.RLock()

    # -- loading -----------------------------------------------------------
    def load(self, force: bool = False) -> bool:
        with self._lock:
            if self.loaded and not force:
                return True
            self.docs = []
            self.tf = []
            self.doc_len = []
            self.df = Counter()
            self.avgdl = 0.0
            self.load_error = None
            if not self.path.is_file():
                self.load_error = f"knowledge file not found: {self.path}"
                self.loaded = False
                return False
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        row = json.loads(line)
                        text = row.get("text") or ""
                        if len(text) < 20:
                            continue
                        title = row.get("title") or ""
                        # Title tokens are repeated to give a modest title boost.
                        tokens = tokenize(title) * 2 + tokenize(text)
                        if not tokens:
                            continue
                        counts = Counter(tokens)
                        self.docs.append(row)
                        self.tf.append(counts)
                        self.doc_len.append(len(tokens))
                        for term in counts:
                            self.df[term] += 1
                if self.docs:
                    self.avgdl = sum(self.doc_len) / float(len(self.doc_len))
                self.loaded = True
                self.loaded_at = time.time()
                manifest_path = self.path.parent / "manifest.json"
                if manifest_path.is_file():
                    try:
                        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        self.manifest = {}
                return True
            except Exception as exc:  # noqa: BLE001
                self.load_error = f"{type(exc).__name__}: {exc}"
                self.loaded = False
                return False

    # -- retrieval ---------------------------------------------------------
    def _score(self, q_terms: List[str], idx: int, k1: float = 1.5, b: float = 0.75) -> float:
        counts = self.tf[idx]
        dl = self.doc_len[idx] or 1
        score = 0.0
        for term in q_terms:
            freq = counts.get(term)
            if not freq:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1.0 + (len(self.docs) - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1.0 - b + b * dl / (self.avgdl or 1.0))
            score += idf * (freq * (k1 + 1.0)) / denom
        return score

    def search(self, query: str, top_k: int = 4, max_per_source: int = 2) -> List[dict]:
        if not self.loaded:
            return []
        q = (query or "").strip()
        if not q:
            return []
        q_terms = tokenize(q, expand=True)
        if not q_terms:
            return []
        q_unique = list(dict.fromkeys(q_terms))
        want_code = bool(CODE_HINTS.search(q.lower()))
        want_pin = bool(PIN_HINTS.search(q.lower()))
        want_exam = bool(EXAM_HINTS.search(q))
        scored: List[Tuple[float, int]] = []
        for idx in range(len(self.docs)):
            s = self._score(q_unique, idx)
            if s <= 0:
                continue
            row = self.docs[idx]
            kind = row.get("kind")
            if kind == "board":
                s *= 1.7
            elif kind in ("code", "ioc"):
                s *= 1.12 if want_code else 0.98
                src = row.get("source") or ""
                # Official module test projects are the best source for
                # board-specific pin/config answers; exam projects often
                # contain board variants and commented-out pin sets.
                if "firmware/" in src:
                    s *= 1.4
                elif "3.测试工程源码" in src:
                    s *= 1.3
                elif "扩展板程序" in src or "程序代码.rar" in src:
                    s *= 1.1
                elif "视频配套" in src:
                    s *= 0.88
            elif kind == "xlsx":
                s *= 1.2 if want_exam else 0.95
            elif kind in ("exam_ocr",):
                s *= 1.15 if want_exam else 1.0
            if OLD_PLATFORM in (row.get("source") or ""):
                s *= 0.72
            if want_pin and kind in ("board", "pdf"):
                s *= 1.15
            if want_exam and row.get("category") in ("省赛真题", "国赛真题", "客观题"):
                s *= 1.25
            scored.append((s, idx))
        scored.sort(reverse=True)
        out: List[dict] = []
        per_source: Counter = Counter()
        best = scored[0][0] if scored else 0.0
        for s, idx in scored:
            row = self.docs[idx]
            source = row.get("source") or ""
            if per_source[source] >= max_per_source:
                continue
            # Keep the tail useful but avoid returning dozens of weak matches.
            if best > 0 and s < best * 0.08 and len(out) >= 2:
                break
            per_source[source] += 1
            item = dict(row)
            item["score"] = round(float(s), 4)
            item["snippet"] = _snippet(row.get("text") or "", q)
            item["label"] = _short_source(row)
            out.append(item)
            if len(out) >= top_k:
                break
        return out

    def build_context(self, query: str, top_k: int = 3, budget: int = 1350,
                      min_score: float = 6.0) -> Tuple[str, List[dict]]:
        hits = [h for h in self.search(query, top_k=top_k) if h.get("score", 0) >= min_score]
        if not hits:
            return "", []
        blocks: List[str] = []
        sources: List[dict] = []
        used = 0
        for n, hit in enumerate(hits, 1):
            text = re.sub(r"\n{2,}", "\n", (hit.get("text") or "").strip())
            # Leave room for source headers and the prompt itself.
            remain = max(220, budget - used - 120)
            if len(text) > remain:
                cut = text[:remain]
                # prefer cutting at a sentence boundary
                for sep in ("。", "；", "\n", "！", "？"):
                    p = cut.rfind(sep)
                    if p > remain * 0.55:
                        cut = cut[:p + 1]
                        break
                text = cut + ("…" if len(text) > len(cut) else "")
            header = f"[{n}] {hit.get('label') or hit.get('title')}"
            block = f"{header}\n{text}"
            if used + len(block) > budget and blocks:
                break
            blocks.append(block)
            used += len(block) + 2
            sources.append({
                "n": n,
                "title": hit.get("title"),
                "label": hit.get("label"),
                "kind": hit.get("kind"),
                "category": hit.get("category"),
                "source": hit.get("source"),
                "score": hit.get("score"),
                "snippet": hit.get("snippet"),
            })
        return "\n\n".join(blocks), sources

    def status(self) -> dict:
        kinds: Counter = Counter(d.get("kind") for d in self.docs)
        categories: Counter = Counter(d.get("category") for d in self.docs)
        return {
            "loaded": self.loaded,
            "path": str(self.path),
            "chunks": len(self.docs),
            "sources": len({d.get("source") for d in self.docs}),
            "kinds": dict(kinds),
            "categories": dict(categories),
            "avg_tokens": round(self.avgdl, 1),
            "loaded_at": self.loaded_at,
            "error": self.load_error,
            "manifest": {
                "built_at": self.manifest.get("built_at"),
                "chunks": self.manifest.get("chunks"),
                "chars": self.manifest.get("chars"),
                "sha256": self.manifest.get("sha256"),
            },
        }

    def is_question(self, text: str) -> bool:
        return bool(QUESTION_RE.search(text or ""))

    def source_dict(self, hit: dict, n: int) -> dict:
        return {
            "n": n,
            "title": hit.get("title"),
            "label": hit.get("label"),
            "kind": hit.get("kind"),
            "category": hit.get("category"),
            "source": hit.get("source"),
            "score": hit.get("score"),
            "snippet": hit.get("snippet"),
        }

    def best_code_chunk(self, hit: dict, query: str) -> dict:
        """Pick the chunk in a source that actually contains the asked API.

        The first chunk of a .c file is mostly includes/comments, which ranks
        well for a short query but is useless as an answer.  Search all chunks
        of the selected source for query terms and prefer a complete function.
        """
        source = hit.get("source")
        same = [d for d in self.docs if d.get("source") == source and d.get("kind") in ("code", "ioc")]
        if not same:
            return hit
        q_terms = [t for t in tokenize(query, expand=True) if len(t) >= 2 and t not in STOPWORDS]
        q_low = (query or "").lower()
        preferred: List[str] = []
        if re.search(r"i2c|iic|24c02|eeprom|读写", q_low):
            preferred += ["24c02", "write", "read"]
        if re.search(r"lcd|液晶|屏幕|显示|字符串", q_low):
            preferred += ["displaystring", "showstring", "displaychar"]
        if re.search(r"led|灯|点亮", q_low):
            preferred += ["led_disp", "led_init"]
        if re.search(r"pwm|占空比", q_low):
            preferred += ["setduty", "pwm"]
        if re.search(r"usart|uart|串口", q_low):
            preferred += ["usart1_init", "mspinit", "uart"]
        if re.search(r"adc|电位器|采样", q_low):
            preferred += ["getadc", "adc1_init"]
        if re.search(r"key|按键", q_low):
            preferred += ["key_scan", "key_init"]
        if re.search(r"rtc|实时时钟", q_low):
            preferred += ["rtc"]
        if re.search(r"输入捕获|capture|测频|频率", q_low):
            preferred += ["pwm_input", "hal_tim_ic", "capture", "tim_ic"]

        def rank(d: dict):
            text = (d.get("text") or "").lower()
            term_hits = sum(min(text.count(t), 6) for t in q_terms if t in text)
            pref_hits = sum(3 for p in preferred if p in text)
            size_penalty = abs(len(d.get("text") or "") - 1200)
            return (term_hits + pref_hits, -size_penalty, len(d.get("text") or ""))

        return max(same, key=rank)

    def board_relevant(self, hit: dict, query: str) -> bool:
        """Only use a board card when its section actually matches the ask."""
        section = ((hit.get("meta") or {}).get("section") or "").lower()
        q = (query or "").lower()
        module_terms = {
            "led": r"led|灯|点亮|gpio",
            "按键": r"按键|key|消抖|松手",
            "adc": r"adc|电位器|采样|模拟",
            "pwm": r"pwm|占空比|tim15",
            "usart": r"usart|uart|串口|波特率",
            "i2c": r"i2c|iic|24c02|eeprom",
            "lcd": r"lcd|液晶|屏幕|显示",
            "rtc": r"rtc|实时时钟|日历",
        }
        if "蓝桥杯大赛与竞赛板" in section:
            return bool(re.search(r"蓝桥杯|比赛|竞赛|省赛|国赛|考点|入门|准备|备考|是什么", q))
        if "已验证引脚与配置" in section:
            # Match the subsection keyword, not just "配置".
            return any(re.search(pat, q) and re.search(pat, section) for pat in module_terms.values())
        if "常见故障速查" in section:
            return bool(re.search(r"不亮|常亮|收不到|乱跳|不变|无波形|花屏|失败|跑飞|找不到|下载成功|复位|排查|故障", q))
        if "调试顺序" in section:
            return bool(re.search(r"调试|排查|顺序|先.*再|步骤", q))
        if "备赛与真题" in section:
            return bool(re.search(r"真题|省赛|国赛|考点|备赛|考试|刷题|比赛|准备|备考", q))
        if "新手最短上手路径" in section:
            return bool(re.search(r"入门|新手|上手|快速|学习路线|怎么学", q))
        if "板载资源" in section or "平台身份" in section or section.startswith("总览"):
            return bool(re.search(r"资源|板载|型号|芯片|平台|是什么|介绍|入门", q))
        if "竞赛常用模块清单" in section:
            return bool(re.search(r"模块清单|考什么|有哪些模块|模块有哪些", q))
        return True

    def module_code(self, query: str) -> Optional[dict]:
        """Find the canonical BSP file for a module mentioned in the query."""
        q = (query or "").lower()
        mapping = (
            (r"led|灯", ("bsp_led.c",)),
            (r"key|按键", ("bsp_key.c",)),
            (r"lcd|液晶|屏幕", ("bsp_lcd.c",)),
            (r"usart|uart|串口", ("bsp_usart.c",)),
            (r"i2c|iic|24c02|eeprom", ("bsp_iic.c", "bsp_i2c.c")),
            (r"adc|电位器|采样", ("bsp_adc.c",)),
            (r"pwm|占空比", ("bsp_pwm.c",)),
            (r"rtc|实时时钟", ("bsp_rtc.c",)),
            (r"tim|定时器", ("bsp_tim.c",)),
        )
        for pattern, filenames in mapping:
            if not re.search(pattern, q):
                continue
            candidates = []
            for d in self.docs:
                meta = d.get("meta") or {}
                if d.get("kind") != "code" or meta.get("file") not in filenames:
                    continue
                src = d.get("source") or ""
                if "firmware/" in src:
                    pri = 0
                elif "3.测试工程源码" in src:
                    pri = 1
                elif "扩展板程序" in src or "程序代码.rar" in src:
                    pri = 2
                else:
                    pri = 3
                candidates.append((pri, d))
            if not candidates:
                continue
            candidates.sort(key=lambda item: item[0])
            seed = dict(candidates[0][1])
            seed["score"] = 10.0
            seed["snippet"] = _snippet(seed.get("text") or "", query)
            seed["label"] = _short_source(seed)
            chunk = self.best_code_chunk(seed, query)
            chunk = dict(chunk)
            text = (chunk.get("text") or "").lower()
            if "i2c" in pattern and not re.search(r"i2c|iic|24c02", text):
                return None
            if "usart" in pattern and not re.search(r"usart|uart", text):
                return None
            if "pwm" in pattern and not re.search(r"pwm|tim", text):
                return None
            if "tim" in pattern:
                if re.search(r"输入捕获|capture|测频|频率", q) and not re.search(r"capture|hal_tim_ic|输入捕获", text):
                    return None
                if not re.search(r"tim", text):
                    return None
            if "adc" in pattern and "adc" not in text:
                return None
            if "led" in pattern and "led" not in text:
                return None
            if "lcd" in pattern and "lcd" not in text:
                return None
            if "key" in pattern and "key" not in text:
                return None
            if "rtc" in pattern and "rtc" not in text:
                return None
            chunk["score"] = seed["score"]
            chunk["snippet"] = _snippet(chunk.get("text") or "", query)
            chunk["label"] = _short_source(chunk)
            return chunk
        return None

    def fast_answer(self, query: str, top_k: int = 8):
        """Return an accurate extractive answer for board/code questions.

        The 0.5B model needs ~19 tokens/s of prompt processing on the Pi 4B,
        so a 1000-token RAG prompt costs ~1 minute.  For the high-value
        beginner questions (pins, modules, code) the retrieved board card and
        source snippet are already the answer; return them directly and keep
        the LLM for open-ended conversation.
        """
        hits = self.search(query, top_k=top_k)
        if not hits or hits[0].get("score", 0) < 7:
            return None
        q_low = (query or "").lower()
        want_code = bool(CODE_HINTS.search(q_low))
        want_exam = bool(EXAM_HINTS.search(query or ""))
        technical = bool(re.search(
            r"nvic|中断|捕获|capture|pwm|usart|uart|串口|i2c|iic|adc|lcd|led|rtc|tim|定时器|寄存器|时钟|优先级",
            q_low,
        ))

        board_hits = [h for h in hits if h.get("kind") == "board" and self.board_relevant(h, query)]
        code_hits = [h for h in hits if h.get("kind") in ("code", "ioc")]
        exam_hits = [h for h in hits if h.get("kind") in ("xlsx", "exam_ocr", "docx")]
        used: List[dict] = []
        parts: List[str] = []

        # Prefer the specific module section over the short "module list" or
        # preamble cards, which otherwise win BM25 on length normalisation.
        generic_sections = ("总览", "1. 平台身份", "2. 板载资源", "5. 竞赛常用模块清单",
                            "7. 调试顺序", "9. 回答口径", "11. 回答口径")
        intro = bool(re.search(r"入门|新手|上手|快速|学习路线|怎么学", query or ""))

        def board_rank(h: dict):
            section = (h.get("meta") or {}).get("section") or ""
            if intro and "上手路径" in section:
                return (0, -h.get("score", 0))
            generic = any(section.startswith(g) for g in generic_sections)
            return (1 if generic else 0, -h.get("score", 0))

        board_hits.sort(key=board_rank)

        if board_hits:
            top = board_hits[0]
            text = clean_excerpt(top.get("text") or "", 620, board=True)
            if text:
                parts.append("**板卡要点**\n" + text)
                used.append(top)

        if want_exam and exam_hits:
            top = exam_hits[0]
            if top.get("kind") == "xlsx":
                # Use the first sheet chunk so the header row is included.
                same = [d for d in self.docs if d.get("source") == top.get("source") and d.get("kind") == "xlsx"]
                if same:
                    top = min(same, key=lambda d: (d.get("meta") or {}).get("part", 999))
                    top = dict(top)
                    top["score"] = exam_hits[0].get("score", 0)
                    top["snippet"] = _snippet(top.get("text") or "", query)
                    top["label"] = _short_source(top)
            text = clean_excerpt(top.get("text") or "", 650, board=False)
            if text:
                parts.append("**考点摘录**\n" + text)
                used.append(top)

        code_top = None if want_exam else self.module_code(query)
        if code_top is None and not want_exam and code_hits and (want_code or (board_hits and code_hits[0].get("score", 0) >= board_hits[0].get("score", 0) * 0.42) or (not board_hits and technical)):
            def code_priority(h: dict):
                src = h.get("source") or ""
                if "firmware/" in src:
                    p = 0
                elif "3.测试工程源码" in src:
                    p = 1
                elif "扩展板程序" in src or "程序代码.rar" in src:
                    p = 2
                else:
                    p = 3
                return (p, -h.get("score", 0))

            seed = sorted(code_hits, key=code_priority)[0]
            code_top = self.best_code_chunk(seed, query)
            code_top = dict(code_top)
            code_top["score"] = seed.get("score")
            code_top["snippet"] = _snippet(code_top.get("text") or "", query)
            code_top["label"] = _short_source(code_top)

        if code_top:
            text = (code_top.get("text") or "").strip()
            if text:
                if code_top.get("kind") != "ioc":
                    text = focus_code(text, query, 700)
                elif len(text) > 700:
                    text = text[:700].rsplit("\n", 1)[0] + "\n; …"
                lang = "ini" if code_top.get("kind") == "ioc" else "c"
                parts.append(
                    f"**参考代码（{code_top.get('label') or code_top.get('title')}）**\n"
                    f"```{lang}\n{text}\n```"
                )
                used.append(code_top)

        text_hits = [h for h in hits if h.get("kind") in ("ppt", "pdf") and h.get("score", 0) >= 15]
        if technical and text_hits and not board_hits:
            top = text_hits[0]
            text = clean_excerpt(top.get("text") or "", 700, board=False)
            if text:
                parts.append(f"**课件/文档摘录（{top.get('label') or top.get('title')}）**\n" + text)
                used.append(top)

        if not parts:
            return None
        # De-duplicate sources while preserving order.
        seen = set()
        unique_used = []
        for h in used:
            key = h.get("id")
            if key in seen:
                continue
            seen.add(key)
            unique_used.append(h)
        if not unique_used:
            return None
        return "\n\n".join(parts), unique_used


def focus_code(text: str, query: str, limit: int = 700) -> str:
    """Start a code excerpt at the function the user actually asked about."""
    text = (text or "").strip()
    q = (query or "").lower()
    anchors: List[str] = []
    if re.search(r"i2c|iic|24c02|eeprom|读写", q):
        anchors = ["//24c02", "iic_24c02_write", "24c02"]
    elif re.search(r"lcd|液晶|屏幕|显示|字符串", q):
        anchors = ["LCD_DisplayStringLine", "LCD_DisplayChar", "LCD_Clear"]
    elif re.search(r"led|灯|点亮", q):
        anchors = ["LED_Disp", "LED_Init"]
    elif re.search(r"pwm|占空比", q):
        anchors = ["PWM_SetDuty", "PWM_Output_TIM15_Init"]
    elif re.search(r"usart|uart|串口", q):
        anchors = ["USART1_Init", "HAL_UART_MspInit"]
    elif re.search(r"adc|电位器|采样", q):
        anchors = ["getADC1", "ADC1_Init"]
    elif re.search(r"key|按键", q):
        anchors = ["Key_Scan", "KEY_Init"]
    elif re.search(r"rtc|实时时钟", q):
        anchors = ["RTC"]
    elif re.search(r"输入捕获|capture|测频|频率", q):
        anchors = ["PWM_Input", "HAL_TIM_IC", "Capture", "TIM_IC"]
    for anchor in anchors:
        idx = text.lower().find(anchor.lower())
        if idx < 0:
            continue
        start = text.rfind("\n", 0, idx)
        start = 0 if start < 0 else start + 1
        # Pull in an immediately preceding comment block (up to 6 lines).
        head = text[:start].split("\n")
        comment_start = start
        for j in range(len(head) - 1, max(-1, len(head) - 7), -1):
            line = head[j].strip()
            if line.startswith(("//", "/*", "*", "*/")) or line == "":
                if line:
                    comment_start = sum(len(x) + 1 for x in head[:j])
            else:
                break
        if comment_start < start and start - comment_start < 300:
            start = comment_start
        text = text[start:]
        break
    if len(text) > limit:
        cut = text[:limit]
        # Prefer a function boundary rather than a random line.
        p = cut.rfind("\n}")
        if p > limit * 0.45:
            cut = cut[:p + 2]
        else:
            cut = cut.rsplit("\n", 1)[0]
        text = cut + "\n// …"
    return text.strip()


def clean_excerpt(text: str, limit: int, board: bool = False) -> str:
    lines: List[str] = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"\d*_?Office 主题", "", s).strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if re.fullmatch(r"[\s|:\-]+", s):
            continue
        if s.startswith("|") and s.endswith("|"):
            s = s.strip("|").replace("|", " · ").strip()
        lines.append(s)
    out = "\n".join(lines).strip()
    if len(out) > limit:
        cut = out[:limit]
        for sep in ("。", "；", "\n", "！", "？"):
            p = cut.rfind(sep)
            if p > limit * 0.55:
                cut = cut[:p + 1]
                break
        out = cut + "…"
    return out


kb = KnowledgeBase()


SYSTEM_PROMPT = """你是蓝桥杯嵌入式 AI 助教，专精 CT117E-M4（STM32G431RBT6，Keil + CubeMX + HAL）。学生多为零基础。
回答要求：先结论，再步骤/代码要点，最后易错点；优先依据【检索资料】，不足时用通用知识简短回答，不编造引脚或代码；也可以正常聊天。
没有联网能力：天气问题只能回答“我无法获取实时天气，请查看手机天气”，不得给出城市、日期、温度等天气细节；日期/星期问题直接使用下方“当前日期”回答。
问“代码是什么”时，用 2–3 句解释：代码是编程语言写成的指令集合，源文件经编译/下载运行；举一个 C 语言例子；不要只回答 STM32 代码。旧平台（F103/STC15）只能参考原理，不能照抄引脚；引用资料标 [1][2]；中文回答，300 字以内，代码用 Markdown。"""


def build_messages(history: List[dict], question: str, context: str,
                   sources: List[dict]) -> List[dict]:
    """Build a compact Qwen prompt: system + at most one prior turn + context."""
    now = datetime.now()
    weekdays = "一二三四五六日"
    current = f"{now.year}年{now.month}月{now.day}日 星期{weekdays[now.weekday()]}"
    msgs: List[dict] = [{
        "role": "system",
        "content": SYSTEM_PROMPT + f"\n当前日期：{current}。",
    }]
    # Long chat history multiplies prompt-processing latency on the Pi.  The
    # retrieval query already includes the previous question for follow-ups,
    # so keep only the immediately preceding user turn when it adds context.
    recent = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]
    recent = recent[-4:]
    if recent and recent[-1].get("role") == "user" and recent[-1].get("content", "").strip() == question.strip():
        recent = recent[:-1]
    # Keep up to four recent messages, each at most 600 chars, but cap the
    # total history at 1500 chars: the llama-server runs with -c 2048.
    selected = []
    budget = 1500
    for m in reversed(recent):
        content = m["content"][:600]
        if len(content) > budget:
            content = content[:budget]
        if content:
            selected.append({"role": m["role"], "content": content})
            budget -= len(content)
        if budget <= 0:
            break
    msgs.extend(reversed(selected))

    if context:
        user = (
            "【检索资料】\n" + context +
            "\n\n【用户问题】\n" + question +
            "\n\n依据资料回答；资料没有的内容要说明不确定。"
        )
    else:
        user = (
            "【检索资料】未命中知识库。\n\n"
            "请直接回答下面的问题，不要复述问题。\n"
            "- 一般概念、代码含义、学习建议：用通用知识简短回答；\n"
            "- 实时天气、新闻、股价等：明确说明无法获取实时数据，不要编造；\n"
            "- 涉及 CT117E-M4 的具体引脚、寄存器、接线：说明不确定，建议查官方资源包。\n\n"
            "【用户问题】\n" + question
        )
    msgs.append({"role": "user", "content": user})
    return msgs
