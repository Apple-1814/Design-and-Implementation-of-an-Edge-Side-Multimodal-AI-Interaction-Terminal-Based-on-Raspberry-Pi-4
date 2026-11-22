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
RETRIEVE_TERMS_RE = re.compile(
    r"stm32|g431|ct117e|蓝桥|嵌入式|单片机|mcu|gpio|引脚|管脚|寄存器|"
    r"中断|定时器|串口|usart|uart|i2c|iic|spi|adc|dac|pwm|占空比|"
    r"lcd|液晶|led|灯|按键|key|rtc|时钟|晶振|eeprom|24c02|"
    r"keil|cube|hal|代码|函数|编译|烧录|下载|调试|swd|jtag|dma|nvic|exti|tim|"
    r"freertos|rtos|原理图|封装|开发板|板卡|真题|省赛|国赛|备赛|考点|"
    r"芯片|flash|ram|主频|电位器|供电|接口|环境|调试器|下载器|命令|ping|"
    r"sizeof|字符串|扩展|排错|排查|启动|外设|模块",
    re.I,
)

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
    "ram": ["sram"],
    "sram": ["ram"],
    "flash": ["128kb"],
    "主频": ["80mhz"],
    "mcu": ["stm32g431rbt6"],
    "keil": ["mdk"],
    "mdk": ["keil"],
    "cubemx": ["cube", "mx"],
    "led1": ["ld1"],
    "led2": ["ld2"],
    "led3": ["ld3"],
    "led4": ["ld4"],
    "led5": ["ld5"],
    "led6": ["ld6"],
    "led7": ["ld7"],
    "led8": ["ld8"],
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
        for part in re.split(r"[_.:/]+", word):
            if len(part) >= 2:
                tokens.append(part)
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

    def should_retrieve(self, query: str) -> bool:
        """Only pay RAG cost for board/technical questions.

        BM25 always returns *something*: a general question such as
        “为什么天是蓝的” matches common bigrams in the board card and would
        otherwise inject irrelevant hardware context into the 0.5B prompt.
        """
        q = query or ""
        if RETRIEVE_TERMS_RE.search(q):
            return True
        # Pin/identifier/number questions: PC8, USART1, TIM15, 9600 ...
        return bool(re.search(r"[A-Za-z]{2,}\d+|\d{3,}", q))

    def lookup_term(self, term: str) -> str:
        """Look up a glossary term by exact match, then longest substring."""
        t = re.sub(r"[\s？?。！!，,、]", "", term or "").lower()
        if not t:
            return ""
        ordered = sorted(CONCEPT_ANSWERS, key=lambda kv: len(kv[0]), reverse=True)
        for key, answer in ordered:
            if key.lower() == t:
                return answer
        # Board-specific qualifiers mean “ask the board card”, not the glossary:
        # 第二路 ADC / RTC 时钟源 / ADC 查询命令 / PWM 设置命令.
        if re.search(
            r"引脚|管脚|数据口|锁存|地址|命令|配置|代码|函数名|时钟源|时钟频率|主频|"
            r"波特率|中断源|通道|第[一二三四五]路|寄存器值|电路|接线|原理图|时序|格式|怎么|如何",
            t,
        ):
            return ""
        # Board identifiers such as USART1 / LED1 / TIM15 must go to the board
        # card, not the generic USART/LED glossary entry.
        if re.search(r"\d", t):
            return ""
        for key, answer in ordered:
            if key.lower() in t:
                return answer
        # Short alias such as “推挽” for “推挽输出”.
        for key, answer in ordered:
            if len(t) >= 2 and t in key.lower():
                return answer
        return ""

    def concept_answer(self, query: str) -> str:
        """Return a curated definition for a standalone “什么是 X” question."""
        return self.lookup_term(query)

    def faq_answer(self, query: str) -> str:
        """Return a curated answer for a few common off-topic questions."""
        q = re.sub(r"[\s？?。！!，,、]", "", query or "")
        q = re.sub(r"^(请问|请|我想问|问一下|我想知道)", "", q)
        for key, answer in FAQ_ANSWERS:
            if key in q and len(q) <= len(key) + 4:
                return answer
        return ""

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
            if re.search(r"初始化|启动|配置|init", q_low):
                preferred += ["pwm_output_tim15_init", "setduty", "pwm"]
            else:
                preferred += ["setduty", "pwm_output_tim15_init", "pwm"]
        if re.search(r"usart|uart|串口", q_low):
            preferred += ["usart1_init", "mspinit", "uart"]
        if re.search(r"adc|电位器|采样", q_low):
            if "getadc1" in q_low:
                preferred += ["getadc1", "adc1_init"]
            elif "getadc2" in q_low:
                preferred += ["getadc2", "adc2_init"]
            elif re.search(r"初始化|配置|init", q_low):
                preferred += ["adc1_init", "adc2_init", "getadc"]
            else:
                preferred += ["getadc", "adc1_init", "adc2_init"]
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
        module_terms = [
            (r"led", r"led|灯|点亮|pc8|pc9|pc10|pc11|pc12|pc13|pc14|pc15|pd2"),
            (r"按键", r"按键|key|消抖|松手|pb0|pb1|pb2|pa0"),
            (r"adc", r"adc|电位器|采样|模拟|pb12|pb15"),
            (r"pwm", r"pwm|占空比|tim15|pa2|pa3"),
            (r"usart", r"usart|uart|串口|波特率|pa9|pa10|sizeof|发送|接收|中断|字符串"),
            (r"i2c|iic", r"i2c|iic|24c02|eeprom|pb6|pb7"),
            (r"lcd", r"lcd|液晶|屏幕|显示"),
            (r"rtc", r"rtc|实时时钟|日历"),
        ]
        if "蓝桥杯大赛与竞赛板" in section:
            return bool(re.search(r"蓝桥杯|比赛|竞赛|省赛|国赛|考点|入门|准备|备考|是什么", q))
        if "已验证引脚与配置" in section:
            # Match the subsection keyword, not just "配置".
            return any(re.search(sp, section) and re.search(qp, q) for sp, qp in module_terms)
        if "回答口径" in section:
            return False
        if "常见故障速查" in section:
            return bool(re.search(r"不亮|常亮|收不到|乱跳|不变|无波形|花屏|失败|跑飞|找不到|下载成功|复位|排查|故障", q))
        if "调试顺序" in section:
            return bool(re.search(r"调试|排查|顺序|先.*再|步骤", q))
        if "备赛与真题" in section:
            return bool(re.search(r"真题|省赛|国赛|考点|备赛|考试|刷题|比赛|准备|备考", q))
        if "新手最短上手路径" in section:
            return bool(re.search(r"入门|新手|上手|快速|学习路线|怎么学", q))
        if "平台身份" in section:
            return bool(re.search(r"型号|芯片|平台|是什么|介绍|主频|flash|ram|sram|mcu|cortex|封装|内存|供电|电源|swd|st-link|调试|下载", q))
        if "板载资源" in section or section.startswith("总览"):
            return bool(re.search(r"资源|板载|型号|芯片|平台|是什么|介绍|入门|接口|J1|J3", q))
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

    def fast_answer(self, query: str, top_k: int = 8, focus: str = ""):
        """Return an accurate extractive answer for board/code questions.

        The 0.5B model needs ~19 tokens/s of prompt processing on the Pi 4B,
        so a 1000-token RAG prompt costs ~1 minute.  For the high-value
        beginner questions (pins, modules, code) the retrieved board card and
        source snippet are already the answer; return them directly and keep
        the LLM for open-ended conversation.
        """
        hits = self.search(query, top_k=max(top_k, 20), max_per_source=6)
        if not hits or hits[0].get("score", 0) < 7:
            return None
        active = (focus or query or "").strip()
        # Ensure board fact cards are considered even when many code chunks
        # dominate BM25.  Code snippets repeat identifiers and can otherwise
        # push the single board card out of the top-k window.
        q_terms = tokenize(query, expand=True)
        board_extra = []
        seen_ids = {h.get("id") for h in hits}
        for idx, row in enumerate(self.docs):
            if row.get("kind") != "board" or row.get("id") in seen_ids:
                continue
            score = self._score(q_terms, idx)
            if score <= 0:
                continue
            item = dict(row)
            item["score"] = score
            item["snippet"] = _snippet(row.get("text") or "", query)
            item["label"] = _short_source(item)
            board_extra.append(item)
        board_extra.sort(key=lambda h: h.get("score", 0), reverse=True)
        hits = board_extra[:6] + hits
        q_low = active.lower()
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
        generic_sections = ("总览", "2. 板载资源", "5. 竞赛常用模块清单",
                            "7. 调试顺序", "9. 回答口径", "11. 回答口径")
        intro = bool(re.search(r"入门|新手|上手|快速|学习路线|怎么学", query or ""))
        module_hints = [
            ("led", r"led", r"led|灯|点亮|pc8|pc9|pc10|pc11|pc12|pc13|pc14|pc15|pd2"),
            ("按键", r"按键", r"按键|key|消抖|松手|pb0|pb1|pb2|pa0"),
            ("adc", r"adc", r"adc|电位器|采样|模拟|pb12|pb15"),
            ("pwm", r"pwm|tim15", r"pwm|占空比|tim15|pa2|pa3"),
            ("usart", r"usart", r"usart|uart|串口|波特率|pa9|pa10|sizeof|发送|接收|中断|字符串"),
            ("i2c", r"i2c|iic", r"i2c|iic|24c02|eeprom|pb6|pb7"),
            ("lcd", r"lcd", r"lcd|液晶|屏幕|显示"),
            ("rtc", r"rtc", r"rtc|实时时钟|日历"),
        ]
        query_modules = {
            name for name, sec_pat, qry_pat in module_hints
            if re.search(qry_pat, q_low)
        }

        def section_module(section: str) -> str:
            section = (section or "").lower()
            for name, sec_pat, _ in module_hints:
                if re.search(sec_pat, section):
                    return name
            return ""

        def board_rank(h: dict):
            section = (h.get("meta") or {}).get("section") or ""
            if intro and "上手路径" in section:
                return (0, 0, -h.get("score", 0))
            match = 0 if section_module(section) in query_modules else 1
            generic = any(section.startswith(g) for g in generic_sections)
            return (match, 1 if generic else 0, -h.get("score", 0))

        board_hits.sort(key=board_rank)
        chosen = []
        seen_sections = set()
        max_sections = 2 if len(query_modules) >= 2 else 1
        for h in board_hits:
            section = (h.get("meta") or {}).get("section") or ""
            if section in seen_sections:
                continue
            seen_sections.add(section)
            chosen.append(h)
            if len(chosen) >= max_sections:
                break
        for top in chosen:
            text = clean_excerpt(top.get("text") or "", 500 if max_sections > 1 else 620, board=True)
            if text:
                section = (top.get("meta") or {}).get("section") or ""
                heading = "**板卡要点" + (f"（{section.split('/')[-1].strip()}）" if max_sections > 1 else "") + "**" + "\n"
                parts.append(heading + text)
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

        code_top = None if want_exam else self.module_code(active)
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
            code_top = self.best_code_chunk(seed, active)
            code_top = dict(code_top)
            code_top["score"] = seed.get("score")
            code_top["snippet"] = _snippet(code_top.get("text") or "", query)
            code_top["label"] = _short_source(code_top)

        if code_top:
            text = (code_top.get("text") or "").strip()
            if text:
                if code_top.get("kind") != "ioc":
                    text = focus_code(text, active, 700)
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
        if re.search(r"初始化|启动|配置|init", q):
            anchors = ["PWM_Output_TIM15_Init", "PWM_SetDuty", "PWM_SetDuty2"]
        else:
            anchors = ["PWM_SetDuty", "PWM_SetDuty2", "PWM_Output_TIM15_Init"]
    elif re.search(r"usart|uart|串口", q):
        anchors = ["USART1_Init", "HAL_UART_MspInit"]
    elif re.search(r"adc|电位器|采样", q):
        if "adc2" in q or "第二路" in q:
            anchors = ["ADC2_Init", "getADC2", "ADC1_Init"]
        elif re.search(r"初始化|配置|init", q):
            anchors = ["ADC1_Init", "ADC2_Init", "getADC1"]
        else:
            anchors = ["getADC1", "ADC2_Init", "ADC1_Init"]
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


SYSTEM_PROMPT = """你是蓝桥杯嵌入式 AI 助教，专精 CT117E-M4（STM32G431RBT6，Keil + CubeMX + HAL），也能正常聊天。学生多为零基础。
回答要求：
- 板卡、外设、代码、比赛类问题：先结论，再给步骤/代码要点，最后易错点；优先依据【检索资料】，资料没有的引脚或寄存器要说明不确定。
- 其他一般问题：用自然段直接回答，2–4 句说清楚；不要套“结论/步骤/易错点”模板，不要重复同一句话。
- 没有联网能力：天气问题只能回答“我无法获取实时天气，请查看手机天气”，不得给出城市、日期、温度等天气细节；日期/星期问题直接使用下方“当前日期”。
- 问“代码是什么”时，用 2–3 句解释：代码是编程语言写成的指令集合，源文件经编译/下载运行；举一个 C 语言例子；不要只回答 STM32 代码。
- 只有提供了【检索资料】时才在句末标注 [1][2]；没有资料时不要编造任何引用或文献。
- 旧平台（F103/STC15）只能参考原理，不能照抄引脚；中文回答，300 字以内，代码用 Markdown。"""


# Deterministic answers for standalone concept questions.  The 0.5B model
# tends to ramble or repeat on "什么是 X"; these cards keep the common terms
# accurate, fast and citation-free.  Longest keys must come first.
CONCEPT_ANSWERS = [
    ("双边沿", "双边沿指上升沿和下降沿都作为有效触发：信号从低到高、从高到低都会触发一次中断或捕获。它适合测量脉冲宽度或需要同时响应两种跳变的场景；配置时把触发极性设为双边沿（如 GPIO_MODE_IT_RISING_FALLING）。"),
    ("边沿检测", "边沿检测是判断信号是否发生跳变：保存上一拍电平，再与当前电平比较，就能区分上升沿（0→1）和下降沿（1→0）。按键扫描、外部中断和输入捕获都依赖边沿检测；软件实现时要在固定周期采样并做消抖。"),
    ("上升沿", "上升沿是信号从低电平跳到高电平的瞬间（0→1）。它常作为外部中断、定时器输入捕获或时钟的有效触发边沿；配置时选择 rising edge，注意信号抖动可能造成多次触发，必要时加硬件或软件消抖。"),
    ("下降沿", "下降沿是信号从高电平跳到低电平的瞬间（1→0）。它常作为外部中断、输入捕获或片选/锁存的有效触发边沿；例如 74HC573 的 LE 在高电平期间透明、下降沿锁存。配置时选择 falling edge，信号抖动大时要加消抖。"),
    ("边沿", "边沿是数字信号电平发生跳变的瞬间：从低到高叫上升沿（0→1），从高到低叫下降沿（1→0）。边沿可用来触发中断、输入捕获或锁存数据；判断边沿要保存上一拍电平并与当前电平比较。"),
    ("中断优先级", "NVIC 用优先级决定谁先响应中断：抢占优先级高的可以打断正在执行的中断，子优先级只在同时挂起时比较；数值越小优先级越高。配置时先分组（如 NVIC_PRIORITYGROUP_4），再用 HAL_NVIC_SetPriority() 设置。中断服务函数要短，避免长延时和 printf。"),
    ("中断", "中断是 CPU 暂停当前程序、转去执行中断服务函数（ISR），处理完再返回原处继续执行的机制。它可由外设或异常触发，如按键 EXTI、USART 接收完成、定时器溢出；NVIC 负责使能和优先级。ISR 要尽量短，只做置标志/存数据，耗时处理放主循环。"),
    ("定时器", "定时器对内部时钟或外部脉冲计数，可实现定时、PWM 输出、输入捕获测频/测占空比、编码器计数。STM32G431 有 TIM1/2/3/4/15/16/17 等；CT117E-M4 的 PWM1/PWM2 用 TIM15 的 CH1/CH2（PA2/PA3），1kHz。"),
    ("串口通信", "串口是异步串行通信：双方按约定波特率、数据位、停止位、校验位，通过 TX/RX 交叉连接逐位传输。CT117E-M4 的 USART1 用 PA9(TX)/PA10(RX)，板载 DAPLink VCP 实测 9600 8N1；GPIO 必须配 AF_PP。收不到数据先查 TX/RX 是否交叉、波特率、AF_PP 和共地。"),
    ("串口", "串口是异步串行通信：双方按约定波特率、数据位、停止位、校验位，通过 TX/RX 交叉连接逐位传输。CT117E-M4 的 USART1 用 PA9(TX)/PA10(RX)，板载 DAPLink VCP 实测 9600 8N1；GPIO 必须配 AF_PP。收不到数据先查 TX/RX 是否交叉、波特率、AF_PP 和共地。"),
    ("通信协议", "通信协议是通信双方约定的数据格式、时序和应答规则，例如帧头、地址、命令、数据、校验、结束符。UART/I2C/SPI 规定电气层和链路层，应用层还要自己定义命令帧；本项目的 Pi↔STM32 就用 9600 8N1 的文本行协议。"),
    ("协议", "通信协议是通信双方约定的数据格式、时序和应答规则，例如帧头、地址、命令、数据、校验、结束符。UART/I2C/SPI 规定电气层和链路层，应用层还要自己定义命令帧；本项目的 Pi↔STM32 就用 9600 8N1 的文本行协议。"),
    ("单片机", "单片机（MCU）是把 CPU、Flash、RAM、定时器、串口、ADC 等外设集成在一颗芯片上的微型计算机。CT117E-M4 使用 STM32G431RBT6：Cortex-M4 内核、128KB Flash、32KB SRAM、最高 80MHz。"),
    ("嵌入式系统", "嵌入式系统是面向特定功能、嵌入到设备内部的专用计算机系统，通常资源受限，强调实时性和可靠性。它由处理器/MCU、外设、固件和应用软件组成；本项目的树莓派 + STM32 终端就是一个边缘 AI 嵌入式系统。"),
    ("嵌入式", "嵌入式系统是面向特定功能、嵌入到设备内部的专用计算机系统，通常资源受限，强调实时性和可靠性。它由处理器/MCU、外设、固件和应用软件组成；本项目的树莓派 + STM32 终端就是一个边缘 AI 嵌入式系统。"),
    ("寄存器", "寄存器是 CPU 或外设内部的可读写硬件单元，配置外设本质就是按数据手册写对应寄存器位。HAL 库把这些操作封装成函数（如 HAL_GPIO_WritePin），但调试时仍需要回查寄存器。读改写时注意不要破坏其他位，常用 |= 和 &=~。"),
    ("时钟", "时钟是 CPU 和外设工作的节拍，频率决定指令与外设速度。STM32G431 板载 HSE 24MHz，经 PLL（M=3,N=20,P=2）得到 80MHz；每个外设还要单独使能时钟（__HAL_RCC_xxx_CLK_ENABLE）。时钟没开，外设配置写了也不会动。"),
    ("晶振", "晶振是利用石英谐振提供稳定频率的振荡器。CT117E-M4 板载 24MHz HSE 供主时钟/PLL，32.768kHz LSE 供 RTC；HSE 起振失败会导致程序卡在时钟初始化。"),
    ("看门狗", "看门狗是一个超时复位计数器：程序正常时定期“喂狗”，跑飞或死循环导致超时，就自动复位系统。STM32 有独立看门狗 IWDG（LSI 驱动）和窗口看门狗 WWDG；调试时可先关闭，量产建议开启。"),
    ("低功耗", "低功耗通过关闭时钟、外设和部分电源，让 MCU 进入 Sleep/Stop/Standby 等模式，再由中断或唤醒源恢复。Stop 模式保留 SRAM 和寄存器，Standby 最省电但会复位；选型时要权衡唤醒时间、功耗和保持内容。"),
    ("轮询", "轮询是主循环反复查询外设状态标志，程序简单但会占用 CPU，响应也不及时。中断是外设事件触发 CPU，效率更高；数据量大时可用 DMA。简单按键/ADC 可以用轮询，串口接收建议中断或 DMA。"),
    ("GPIO", "GPIO 是通用输入输出引脚，可配置为输入、输出、复用功能或模拟模式；输出有推挽/开漏，输入可加上下拉。CT117E-M4 的 LED 用 PC8–PC15（低电平点亮，PD2 锁存），按键用 PB0/PB1/PB2/PA0。"),
    ("PWM", "PWM 是脉冲宽度调制：保持周期不变，改变高电平时间（占空比），用等效值控制亮度、电机速度或输出电压。CT117E-M4 的 PWM1/PWM2 是 PA2/PA3（TIM15 CH1/CH2），1kHz；占空比 0–100% 对应比较值 0–1000。"),
    ("ADC", "ADC 把模拟电压转换成数字量。CT117E-M4 用 12 位 ADC：ADC1=PB12（IN11）、ADC2=PB15（IN15），结果 0–4095 对应 0–3.3V。采样后可做多次平均、中值或一阶低通滤波，电位器变化才能稳定显示。"),
    ("DAC", "DAC 把数字量转换成模拟电压，可用于输出设定电压或波形。STM32G431 部分型号带 DAC，具体通道和引脚要以数据手册/板卡原理图为准；本板课程例程主要用 PWM 做等效模拟输出。"),
    ("I2C", "I2C 是两线同步串行总线：SCL 时钟、SDA 数据，开漏输出并接上拉，支持多设备 7 位地址。CT117E-M4 用 PB6/PB7 接 AT24C02，EEPROM 地址 0x50；通信要处理起始/停止、应答和页写边界。"),
    ("IIC", "I2C 是两线同步串行总线：SCL 时钟、SDA 数据，开漏输出并接上拉，支持多设备 7 位地址。CT117E-M4 用 PB6/PB7 接 AT24C02，EEPROM 地址 0x50；通信要处理起始/停止、应答和页写边界。"),
    ("SPI", "SPI 是四线同步串行总线：SCK、MOSI、MISO、NSS，全双工、速度快，但每增加一个从机通常多一根片选。具体引脚以板卡原理图为准；配置时注意时钟极性 CPOL、相位 CPHA 和片选时序。"),
    ("UART", "UART 是异步串行通信接口，双方按约定波特率、数据位、停止位和校验位，通过 TX/RX 交叉连接传输。CT117E-M4 的 USART1 用 PA9/PA10，板载 VCP 实测 9600 8N1，GPIO 必须配 AF_PP。"),
    ("USART", "USART 是带同步/异步模式的串行接口；本板用异步模式，即常说的 UART。CT117E-M4 的 USART1 用 PA9(TX)/PA10(RX)，板载 VCP 实测 9600 8N1，GPIO 必须配 AF_PP。"),
    ("RTC", "RTC 是独立运行的实时时钟，持续计年月日时分秒，常由 32.768kHz LSE 供时钟。STM32 用 HAL_RTC_SetTime/SetDate 设置，读取时先 GetTime 再 GetDate；注意 BCD 格式和首次初始化。"),
    ("DMA", "DMA 是直接内存访问：外设和内存之间搬数据时不占 CPU，适合串口收发、ADC 连续采样和 LCD 刷屏。使用时要配通道、传输方向、数据宽度和完成中断；注意缓冲区生命周期。"),
    ("NVIC", "NVIC 是 Cortex-M 的嵌套向量中断控制器，负责中断使能、挂起、优先级和嵌套。抢占优先级决定能否打断当前 ISR，子优先级只在同时挂起时比较，数值越小越高；用 HAL_NVIC_SetPriority 和 HAL_NVIC_EnableIRQ 配置。"),
    ("RTOS", "RTOS 是实时操作系统，用任务调度、队列、信号量和延时管理多个功能，让程序结构从大循环变成多任务。FreeRTOS 是常用开源实现；课程例程以裸机为主，模块多、时序复杂时再考虑引入。"),
    ("FreeRTOS", "FreeRTOS 是常用的开源实时操作系统，提供任务调度、队列、信号量、软件定时器等机制。它适合功能多、时序复杂的项目；蓝桥杯课程例程以裸机为主，初学先把中断和状态机写好。"),
    ("HAL", "HAL 是 ST 的硬件抽象层库，把寄存器操作封装成 HAL_xxx_Init/Start/Write 等函数，CubeMX 可生成初始化代码。它移植方便但代码体积和开销略大；比赛时常用 HAL + 少量寄存器/LL 操作。"),
    ("DSP", "DSP 指数字信号处理，包括滤波、FFT、卷积等算法。STM32G431 的 Cortex-M4 带 FPU 和 DSP 指令，可用 CMSIS-DSP 库加速；运算量大时注意采样率、内存和定点/浮点选择。"),
    ("Bootloader", "Bootloader 是上电后先运行的一段程序，负责升级固件或跳转到应用程序。STM32 可通过串口/CAN/USB 等做 IAP；CT117E-M4 平时用 CMSIS-DAP 直接烧录，一般不需要自己写 Bootloader。"),
    ("中断服务函数", "中断服务函数（ISR）是中断触发后由 CPU 自动调用的函数，用来尽快处理事件：清中断标志、读数据、置标志位。函数名必须和启动文件/向量表一致（如 EXTI0_IRQHandler、USART1_IRQHandler）；ISR 要短，不要长延时、printf 或大运算。"),
    ("中断嵌套", "中断嵌套是高优先级中断打断正在执行的低优先级 ISR。NVIC 的抢占优先级决定能否嵌套，子优先级只在同时挂起时排队；嵌套层数越多，栈开销越大，调试时要注意。"),
    ("外部中断", "外部中断由 GPIO 电平跳变触发（EXTI），可配置上升沿、下降沿或双边沿，再经 NVIC 使能。CT117E-M4 按键用 PB0/PB1/PB2/PA0；ISR 里要清中断标志。"),
    ("EXTI", "EXTI 是 STM32 的外部中断/事件控制器，把 GPIO 跳变映射到中断线（EXTI0–15），可独立选择上升沿、下降沿或双边沿触发。配置顺序：GPIO 输入 → EXTI 触发方式 → NVIC 使能 → 写 ISR 并清标志。"),
    ("HardFault", "HardFault 是 Cortex-M 的严重异常，常见于野指针、数组越界、栈溢出、非对齐访问或调用空函数指针。调试时在 HardFault_Handler 下断点，查看 LR/PC 和堆栈，再回溯出错地址。"),
    ("输入捕获", "输入捕获用定时器记录指定边沿到来时的计数器值，两次捕获之差就是脉冲间隔，可用于测频率、周期和占空比。配置时选通道、极性、捕获边沿和中断；计数器溢出时要补偿。"),
    ("预分频", "预分频（Prescaler）把定时器时钟先分频再计数，降低计数频率、扩大定时范围。实际计数时钟 = 定时器时钟 / (PSC+1)；PWM 里 PSC 和 ARR 一起决定频率。"),
    ("自动重装载", "自动重装载寄存器（ARR）决定计数器计到多少后归零或翻转，和预分频一起决定定时周期或 PWM 频率。PWM 频率 = 定时器时钟 / ((PSC+1)*(ARR+1))。"),
    ("占空比", "占空比是一个周期内高电平时间所占的比例，0% 全低、100% 全高。PWM 用它控制亮度、速度或等效电压；CT117E-M4 的 PWM 用比较值 0–1000 对应 0–100%。"),
    ("波特率", "波特率是串口每秒传输的码元数，常用 9600、115200；双方必须一致，否则收到乱码。本板 DAPLink VCP 实测只稳定支持 9600 8N1，改 115200 会阻塞。"),
    ("校验位", "校验位是串口帧里用于简单检错的 1 位（无/奇/偶校验），收发双方必须一致。它只能发现部分错误，不能纠错；工业协议通常还会加 CRC。"),
    ("停止位", "停止位是串口一帧数据结束的标志位，常见 1 位或 2 位，收发双方必须一致。9600 8N1 就表示 8 数据位、无校验、1 停止位。"),
    ("全双工", "全双工指双方可以同时收发，例如 UART 的 TX/RX 各一根线、SPI 的 MOSI/MISO。半双工则同一时刻只能一个方向，例如 RS485 两线总线。"),
    ("半双工", "半双工指同一时刻只能一个方向通信，例如 RS485 两线总线需要方向控制；全双工可以同时收发，例如 UART 的 TX/RX、SPI 的 MOSI/MISO。"),
    ("一阶低通", "一阶低通滤波用 `y += (x - y) / N`（或 `y = αx + (1-α)y`）平滑采样值，N/α 越大越平稳但响应越慢。适合 ADC 电位器等慢变量，不能替代硬件滤波。"),
    ("中值滤波", "中值滤波把连续 N 次采样排序后取中间值，能去掉偶发尖峰/毛刺，N 常取 5 或 7。它对缓变信号有效，但计算量比平均滤波大。"),
    ("均值滤波", "均值滤波把连续 N 次采样相加取平均，能抑制随机噪声，N 常取 8/16；代价是响应变慢，采样窗口内的真实变化会被抹平。"),
    ("滤波", "滤波是抑制噪声、保留有用信号的处理。常用方法：多次采样平均、中值滤波去尖峰、一阶低通平滑；模拟端还可加 RC 低通和去耦电容。"),
    ("参考电压", "参考电压（VREF+）是 ADC 的满量程基准，12 位 ADC 的码值 0–4095 对应 0–VREF。CT117E-M4 按 3.3V 计算，所以 4095≈3.3V；VREF 不稳会导致所有采样值漂移。"),
    ("采样时间", "采样时间是 ADC 对输入电容充电的时间，越长越准但转换越慢。高阻信号源需要更长采样时间；CT117E-M4 例程用 640.5 个周期。"),
    ("分辨率", "分辨率是 ADC 能区分的最小电压变化。12 位 ADC 把 0–3.3V 分成 4096 份，1 LSB≈0.806mV；位数越高越精细，但受噪声和参考电压限制。"),
    ("推挽输出", "推挽输出用上下两个 MOS 管分别拉高/拉低，能主动输出高电平和低电平，驱动能力强。USART TX、LED、PWM 等多数输出用推挽；多个推挽输出不能直接并联。"),
    ("开漏输出", "开漏输出只能主动拉低，高电平靠外部上拉电阻，适合 I2C 等共享总线或多电压电平转换。开漏不能直接驱动需要高电平电流的负载；I2C 的 SCL/SDA 必须开漏加上拉。"),
    ("上拉电阻", "上拉电阻把引脚默认拉到高电平，避免悬空误触发，并为开漏总线提供高电平。阻值太大会使上升沿变慢，太小会增加功耗；按键常用 10kΩ 量级。"),
    ("下拉电阻", "下拉电阻把引脚默认拉到低电平，避免输入悬空；按键接法不同时用上拉或下拉，保证松开时电平确定。阻值要与驱动能力和功耗权衡。"),
    ("上拉", "上拉是把引脚通过电阻接到 VCC，使默认电平为高；开漏总线和按键输入常用。阻值太大会使上升沿变慢，太小会增加功耗。"),
    ("下拉", "下拉是把引脚通过电阻接到 GND，使默认电平为低，避免输入悬空。按键接法不同时用上拉或下拉，保证松开时电平确定。"),
    ("状态机", "状态机把程序分成若干状态，每个状态根据输入决定动作和下一个状态，适合按键、菜单、通信协议解析。常用 switch-case 或状态表实现；相比长延时，状态机不阻塞主循环。"),
    ("消抖", "按键消抖是消除机械触点抖动带来的多次误触发。软件做法：检测到变化后延时 10–20ms 再采样，或连续多次采样一致才确认；不要在中断里长延时。"),
    ("栈溢出", "栈溢出是函数调用、局部变量或中断嵌套占用的栈超过预留大小，冲掉其他内存。常见于大局部数组、深递归、ISR 里做大运算；可增大启动文件里的 Stack_Size，并避免在栈上放超大缓冲区。"),
    ("数组越界", "数组越界是访问了数组下标范围之外的内存，会踩坏相邻变量、栈或外设数据，常表现为跑飞、HardFault 或数据莫名变化。C 语言不检查边界，循环条件和字符串长度要特别小心。"),
    ("野指针", "野指针是指向已释放内存、未初始化地址或越界地址的指针，解引用会读写非法内存，导致跑飞或 HardFault。指针定义后立即初始化，free 后置 NULL，使用前检查范围。"),
    ("内存泄漏", "内存泄漏是 malloc 申请的内存没有 free，程序运行越久可用堆越少，最终分配失败。单片机项目更推荐静态分配或内存池；必须动态分配时，确保每条失败/异常路径都释放。"),
    ("栈", "栈用于存放函数返回地址、局部变量和中断现场，由编译器自动管理，通常从 RAM 高端向下增长。栈太小会溢出，太大浪费 RAM；启动文件里的 Stack_Size 可调。"),
    ("堆", "堆用于 malloc/free 动态分配，从 RAM 中划出一块区域，由程序手动管理。单片机项目更推荐静态分配或内存池；动态分配要检查返回值并避免碎片。"),
    ("启动文件", "启动文件（startup_*.s）定义中断向量表、复位入口和默认中断处理函数，并在进入 main 前初始化栈、堆和 .data/.bss 段。中断函数名必须和向量表一致。"),
    ("复位", "复位让 MCU 回到初始状态，重新从启动文件/Reset_Handler 执行。常见来源：上电复位、NRST 引脚、看门狗、软件复位；复位后外设寄存器恢复默认，RTC/备份域可能保持。"),
]


# Small deterministic FAQ for common off-topic/demo questions that the 0.5B
# handles poorly (it tends to confuse “天是蓝的” with weather).
FAQ_ANSWERS = [
    (
        "为什么天是蓝的",
        "天空呈蓝色主要是瑞利散射：太阳光进入大气后，波长较短的蓝光比红光更容易被空气分子散射，从各个方向进入眼睛，所以天空看起来是蓝的。日出日落时阳光穿过更厚的大气，蓝光被散射掉，天空和太阳偏红。",
    ),
    (
        "天为什么是蓝的",
        "天空呈蓝色主要是瑞利散射：太阳光进入大气后，波长较短的蓝光比红光更容易被空气分子散射，从各个方向进入眼睛，所以天空看起来是蓝的。日出日落时阳光穿过更厚的大气，蓝光被散射掉，天空和太阳偏红。",
    ),
    (
        "天空为什么是蓝",
        "天空呈蓝色主要是瑞利散射：太阳光进入大气后，波长较短的蓝光比红光更容易被空气分子散射，从各个方向进入眼睛，所以天空看起来是蓝的。日出日落时阳光穿过更厚的大气，蓝光被散射掉，天空和太阳偏红。",
    ),
    (
        "代码是什么",
        "代码是程序员用编程语言写下的指令集合，描述“做什么、按什么顺序做”。例如 C 语言 `int main(void) { return 0; }` 就是一个最小程序；源文件经编译、链接生成可执行文件，再下载到单片机或由操作系统运行。代码不是 STM32 专属，换平台主要换外设库和编译工具。",
    ),
    (
        "什么是代码",
        "代码是程序员用编程语言写下的指令集合，描述“做什么、按什么顺序做”。例如 C 语言 `int main(void) { return 0; }` 就是一个最小程序；源文件经编译、链接生成可执行文件，再下载到单片机或由操作系统运行。代码不是 STM32 专属，换平台主要换外设库和编译工具。",
    ),
    (
        "程序是什么",
        "程序是为了完成某个任务而组织起来的一组指令和数据。源代码经编译/链接变成可执行文件，运行时由 CPU 逐条执行；单片机程序通常从 `main()` 开始，先初始化时钟和外设，再进入主循环。",
    ),
    (
        "什么是程序",
        "程序是为了完成某个任务而组织起来的一组指令和数据。源代码经编译/链接变成可执行文件，运行时由 CPU 逐条执行；单片机程序通常从 `main()` 开始，先初始化时钟和外设，再进入主循环。",
    ),
    (
        "程序跑飞",
        "程序跑飞常见原因：数组越界或野指针、栈溢出、中断优先级/回调配置错误、死循环没喂狗、时钟或外设未初始化。排查时先在 HardFault_Handler 下断点，查看 LR/PC 和堆栈，再检查大数组、递归和中断里的长延时；必要时开 IWDG 做复位兜底。",
    ),
    (
        "跑飞",
        "程序跑飞常见原因：数组越界或野指针、栈溢出、中断优先级/回调配置错误、死循环没喂狗、时钟或外设未初始化。排查时先在 HardFault_Handler 下断点，查看 LR/PC 和堆栈，再检查大数组、递归和中断里的长延时；必要时开 IWDG 做复位兜底。",
    ),
]


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
            "\n\n依据资料回答；资料没有的内容要说明不确定；资料与问题无关时忽略资料。"
        )
    else:
        user = (
            "【检索资料】未命中知识库。\n\n"
            "请直接回答下面的问题，不要复述问题，也不要重复句子。\n"
            "没有检索资料，不要标注 [1][2] 或编造参考文献。\n"
            "- 一般概念、代码含义、学习建议：用通用知识简短回答；\n"
            "- 实时天气、新闻、股价等：明确说明无法获取实时数据，不要编造；\n"
            "- 涉及 CT117E-M4 的具体引脚、寄存器、接线：说明不确定，建议查官方资源包。\n\n"
            "【用户问题】\n" + question
        )
    msgs.append({"role": "user", "content": user})
    return msgs
