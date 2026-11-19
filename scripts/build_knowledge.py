#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a board-specific knowledge base from the Lanqiao Cup tutorial pack.

The tutorial pack is treated as read-only input.  This script extracts text
from PDF/DOCX/XLSX/legacy-PPT, pulls only application source files out of the
source archives, chunks everything, and writes JSONL for the Pi-side BM25
retriever.

Usage:
    python scripts/build_knowledge.py
    python scripts/build_knowledge.py --kb "D:/path/to/tutorial" --out knowledge
    python scripts/build_knowledge.py --no-archives
    python scripts/build_knowledge.py --ocr-docx

The output is deliberately kept outside the repository history; see
.gitignore (knowledge/, .tmp/).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KB = Path(r"D:\BaiduNetdiskDownload\蓝桥杯嵌入式教程完整版（去加密）")
DEFAULT_OUT = ROOT / "knowledge"
DEFAULT_WORK = ROOT / ".tmp" / "kb_extract"
SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")

# Legacy PowerPoint text atoms (MS-PPT).
TEXT_CHARS_ATOM = 0x0FA0
TEXT_BYTES_ATOM = 0x0FA8
CSTRING_ATOM = 0x0FBA

SKIP_PPT_LINES = (
    "单击此处编辑母版",
    "编辑母版文本样式",
    "单击此处编辑母版标题样式",
)

CODE_SUFFIXES = {".c", ".h", ".ioc"}
EXCLUDE_CODE_PARTS = {
    "drivers", "cmsis", "middlewares", "mdk-arm", "objects", "listings",
    "rte", "debugconfig", "settings", ".git", "__pycache__",
}
INCLUDE_CODE_PARTS = {
    "core", "bsp", "user", "hardware", "app", "application", "modules",
    "src", "inc", "source", "include",
}
GENERATED_CODE_NAMES = {
    "system_stm32g4xx.c", "system_stm32g4xx.h",
}

ARCHIVE_PRIORITY = (
    "测试工程源码",
    "视频配套源代码",
    "视频配套代码",
    "扩展板程序",
    "Object_Project",
    "资源数据包_嵌入式（G431）",
    "程序代码.rar",
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


def clean_prose(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x0b", "\n").replace("\x0c", "\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\u3000]+", " ", line).strip()
        if line:
            lines.append(line)
    # collapse more than one blank line; keep paragraph boundaries
    out = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).strip()


def clean_code(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "").replace("\x00", "")
    return text.strip()


def printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    good = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    return good / len(text)


def read_text_file(path: Path, limit: int = 2_000_000) -> str:
    raw = path.read_bytes()[:limit]
    if not raw:
        return ""
    if raw.count(b"\x00") > max(8, len(raw) // 20):
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            if printable_ratio(text) >= 0.85:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def relative_to(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def category_for(path: Path, kb: Path) -> str:
    rel = relative_to(path, kb)
    first = rel.split("/", 1)[0]
    mapping = {
        "1.零基础入门教程": "入门",
        "2.零基础到真题过渡教程": "过渡",
        "3.历年省赛真题教程": "省赛真题",
        "4.客观题省国赛通用教程": "客观题",
        "5.历年国赛真题教程": "国赛真题",
        "蓝桥杯笔记": "笔记",
        "自己整理的嵌入式资料，希望可以帮到您": "资料",
        "破解的所有视频都在这里面": "视频配套",
    }
    return mapping.get(first, first if first else "其他")


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；!?;])\s*|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_prose(text: str, max_chars: int = 850, overlap: int = 100) -> list[str]:
    """Chunk prose on paragraph/sentence boundaries with a small overlap."""
    text = clean_prose(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = split_sentences(text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            for sent in split_sentences(para):
                if len(sent) > max_chars:
                    step = max_chars - overlap
                    for i in range(0, len(sent), step):
                        chunks.append(sent[i:i + max_chars].strip())
                elif len(buf) + len(sent) + 1 <= max_chars:
                    buf = (buf + "\n" + sent).strip()
                else:
                    if buf:
                        chunks.append(buf.strip())
                    buf = sent
        elif len(buf) + len(para) + 2 <= max_chars:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf.strip())
            buf = para
    if buf.strip():
        chunks.append(buf.strip())
    # add overlap from the previous chunk where it is cheap and useful
    out: list[str] = []
    prev_tail = ""
    for ch in chunks:
        if not ch:
            continue
        if prev_tail and overlap > 0 and len(ch) + len(prev_tail) <= max_chars + overlap:
            ch = prev_tail + "\n" + ch
        out.append(ch)
        prev_tail = ch[-overlap:]
    return out


# ---------------------------------------------------------------------------
# Legacy PPT (.ppt) extraction via OLE "PowerPoint Document" text atoms
# ---------------------------------------------------------------------------

def _decode_ppt_atom(raw: bytes, rectype: int) -> str:
    if rectype == TEXT_BYTES_ATOM:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", "ignore")
    else:
        text = raw.decode("utf-16le", "ignore")
    text = text.replace("\r", "\n").replace("\x0b", "\n")
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t ")
    return clean_prose(text)


def extract_ppt_atoms(path: Path) -> list[str]:
    """Return text atoms in document order from a legacy .ppt file."""
    try:
        import olefile
    except Exception:
        return []
    try:
        with olefile.OleFileIO(str(path)) as ole:
            if not ole.exists("PowerPoint Document"):
                return []
            data = ole.openstream("PowerPoint Document").read()
    except Exception:
        return []

    atoms: list[str] = []
    seen: set[str] = set()
    i = 0
    n = len(data)
    while i + 8 <= n:
        rectype = struct.unpack_from("<H", data, i + 2)[0]
        if rectype in (TEXT_CHARS_ATOM, TEXT_BYTES_ATOM, CSTRING_ATOM):
            verinst = struct.unpack_from("<H", data, i)[0]
            length = struct.unpack_from("<I", data, i + 4)[0]
            rec_ver = verinst & 0x000F
            if rec_ver == 0 and 2 <= length <= 100_000 and i + 8 + length <= n:
                raw = data[i + 8:i + 8 + length]
                text = _decode_ppt_atom(raw, rectype)
                if text and printable_ratio(text) >= 0.8 and not text.startswith("___PPT"):
                    key = re.sub(r"\s+", "", text)
                    if key not in seen and not any(s in text for s in SKIP_PPT_LINES):
                        if text not in ("*", "-", "•"):
                            seen.add(key)
                            atoms.append(text)
                i += 8 + length
                continue
        i += 1
    return atoms


# ---------------------------------------------------------------------------
# PDF / DOCX / XLSX extraction
# ---------------------------------------------------------------------------

def extract_pdf_pages(path: Path) -> Iterator[tuple[int, str]]:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return
    try:
        doc = fitz.open(str(path))
    except Exception:
        return
    for pno, page in enumerate(doc, 1):
        try:
            text = page.get_text("text")
        except Exception:
            text = ""
        yield pno, clean_prose(text)


def extract_docx_parts(path: Path) -> tuple[list[str], int]:
    try:
        from docx import Document
    except Exception:
        return [], 0
    try:
        doc = Document(str(path))
    except Exception:
        return [], 0
    parts: list[str] = []
    for p in doc.paragraphs:
        t = clean_prose(p.text)
        if t:
            parts.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [clean_prose(c.text).replace("\n", " ") for c in row.cells]
            cells = [c for c in cells if c]
            if cells:
                parts.append(" | ".join(cells))
    try:
        with zipfile.ZipFile(path) as z:
            image_count = len([n for n in z.namelist() if n.startswith("word/media/")])
    except Exception:
        image_count = 0
    return parts, image_count


def extract_docx_images(path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    images: list[Path] = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith("word/media/") and name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".bmp", ".webp")
                ):
                    dest = out_dir / Path(name).name
                    dest.write_bytes(z.read(name))
                    images.append(dest)
    except Exception:
        pass
    return images


def extract_xlsx_parts(path: Path) -> list[str]:
    try:
        import openpyxl
    except Exception:
        return []
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception:
        return []
    parts: list[str] = []
    for ws in wb.worksheets:
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            vals = []
            for v in row:
                if v is None:
                    continue
                s = str(v).strip()
                if s and s != "None":
                    vals.append(s)
            if vals:
                rows.append(" | ".join(vals))
        if rows:
            parts.append(f"工作表：{ws.title}\n" + "\n".join(rows))
    try:
        wb.close()
    except Exception:
        pass
    return parts


# ---------------------------------------------------------------------------
# Code extraction and chunking
# ---------------------------------------------------------------------------

def is_useful_code(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in CODE_SUFFIXES:
        return False
    if path.stat().st_size > 200_000:
        return False
    if path.name.lower() in GENERATED_CODE_NAMES:
        return False
    parts = [p.lower() for p in path.parts]
    if any(p in EXCLUDE_CODE_PARTS for p in parts):
        return False
    if suffix == ".ioc":
        return True
    return any(p in INCLUDE_CODE_PARTS for p in parts[:-1])


def _looks_like_function_start(line: str) -> bool:
    s = line.strip()
    if not s.endswith("{") or s.startswith(("if", "for", "while", "switch", "else", "do", "typedef", "struct", "enum", "union")):
        return False
    if "(" not in s or ")" not in s:
        return False
    if re.match(r"^(?:static\s+)?(?:inline\s+)?[A-Za-z_][\w\s\*]*\b[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{$", s):
        return True
    # multi-line signature ending with "{" is handled by the caller
    return bool(re.search(r"\)\s*\{$", s)) and not re.match(r"^(if|for|while|switch|else|do)\b", s)


def chunk_code(text: str, file_hint: str = "", max_chars: int = 1500) -> list[str]:
    text = clean_code(text)
    if not text:
        return []
    lines = text.split("\n")
    chunks: list[str] = []
    i = 0
    while i < len(lines):
        start = i
        # attach a short comment block immediately above the function
        j = i
        while j > 0 and j - 1 >= 0 and lines[j - 1].strip().startswith(("//", "/*", "*", "*/")):
            j -= 1
        sig = lines[i].strip()
        if _looks_like_function_start(sig):
            depth = sig.count("{") - sig.count("}")
            k = i + 1
            while k < len(lines) and depth > 0:
                depth += lines[k].count("{") - lines[k].count("}")
                k += 1
            block = "\n".join(lines[j:k]).strip()
            if len(block) > max_chars:
                # split very long functions by line windows with overlap
                blines = block.split("\n")
                step = 110
                for a in range(0, len(blines), step):
                    sub = "\n".join(blines[a:a + step + 10]).strip()
                    if sub:
                        chunks.append(sub)
            elif block:
                chunks.append(block)
            i = max(k, i + 1)
            continue
        # no function: emit a window of lines
        if i == start:
            block = "\n".join(lines[i:i + 110]).strip()
            if block:
                chunks.append(block)
            i += 100
    # file-level header / macro chunk
    header = "\n".join(lines[:80]).strip()
    if header and (not chunks or header not in chunks[0]):
        if len(header) > max_chars:
            header = header[:max_chars]
        chunks.insert(0, header)
    # dedupe adjacent / identical chunks
    out: list[str] = []
    seen: set[str] = set()
    for ch in chunks:
        key = re.sub(r"\s+", "", ch)
        if len(key) < 20 or key in seen:
            continue
        seen.add(key)
        out.append(ch)
    return out


def code_title(path: Path, project: str) -> str:
    return f"{project} / {path.name}" if project else path.name


def archive_priority(path: Path) -> tuple[int, str]:
    s = str(path)
    for idx, key in enumerate(ARCHIVE_PRIORITY):
        if key in s:
            return idx, s
    return len(ARCHIVE_PRIORITY), s


def discover_archives(kb: Path, max_size: int = 450 * 1024 * 1024) -> list[Path]:
    archives: list[Path] = []
    for p in kb.rglob("*"):
        if p.suffix.lower() not in {".rar", ".zip", ".7z"} or not p.is_file():
            continue
        s = str(p)
        if "破解的所有视频都在这里面" in s:
            continue
        if "竞赛用软件" in s or "芯片资料" in s:
            continue
        if p.name == "蓝桥杯嵌入式资料.zip":
            continue
        if p.stat().st_size > max_size:
            continue
        if not any(k in s for k in ARCHIVE_PRIORITY):
            continue
        archives.append(p)
    archives.sort(key=archive_priority)
    # dedupe identical archives by content hash (duplicate copies in the pack)
    seen: set[str] = set()
    unique: list[Path] = []
    for p in archives:
        try:
            h = sha1_bytes(p.read_bytes())
        except Exception:
            continue
        if h in seen:
            continue
        seen.add(h)
        unique.append(p)
    return unique


def extract_archive_sources(archive: Path, dest: Path, seven_zip: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(seven_zip), "x", "-y", "-r", f"-o{dest}", str(archive),
        "*.c", "*.h", "*.ioc",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=900)
    except Exception as exc:
        log(f"  archive failed: {archive.name}: {exc}")
        return False
    if proc.returncode not in (0, 1):
        log(f"  archive rc={proc.returncode}: {archive.name}")
        return False
    return True


# ---------------------------------------------------------------------------
# Optional OCR for image-only exam compilations
# ---------------------------------------------------------------------------

def ocr_images(images: list[Path], max_images: int = 0) -> list[str]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return []
    try:
        engine = RapidOCR()
    except Exception as exc:
        log(f"  OCR init failed: {exc}")
        return []
    texts: list[str] = []
    for idx, img in enumerate(images[:max_images] if max_images else images, 1):
        try:
            result, _ = engine(str(img))
            if result:
                lines = [str(item[1]).strip() for item in result if len(item) > 1 and str(item[1]).strip()]
                if lines:
                    texts.append("\n".join(lines))
        except Exception:
            continue
        if idx % 10 == 0:
            log(f"  OCR {idx}/{len(images)}")
    return texts


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, kb: Path, out: Path, work: Path, seven_zip: Path):
        self.kb = kb
        self.out = out
        self.work = work
        self.seven_zip = seven_zip
        self.chunks: list[dict] = []
        self.seen_text: set[str] = set()
        self.seen_sources: set[str] = set()
        self.stats: Counter = Counter()
        self.warnings: list[str] = []
        self.source_files: set[str] = set()

    def add(self, title: str, source: str, kind: str, text: str,
            category: str = "", meta: dict | None = None) -> None:
        text = text.strip()
        if len(text) < 25:
            return
        norm = re.sub(r"\s+", "", text)
        if norm in self.seen_text:
            return
        self.seen_text.add(norm)
        meta = dict(meta or {})
        cid = sha1_text(f"{source}|{title}|{text[:300]}")[:16]
        self.chunks.append({
            "id": cid,
            "title": title,
            "source": source,
            "kind": kind,
            "category": category,
            "text": text,
            "meta": meta,
        })
        self.stats[kind] += 1
        self.stats["chars"] += len(text)
        self.source_files.add(source)

    # -- documents ---------------------------------------------------------
    def build_ppt(self, path: Path) -> None:
        atoms = extract_ppt_atoms(path)
        if not atoms:
            self.warnings.append(f"PPT 无文本：{relative_to(path, self.kb)}")
            return
        title = path.stem
        source = relative_to(path, self.kb)
        category = category_for(path, self.kb)
        # group atoms into ~850-char chunks, preserving atom boundaries
        buf: list[str] = []
        size = 0
        for atom in atoms:
            if size + len(atom) > 850 and buf:
                self.add(title, source, "ppt", "\n".join(buf), category)
                buf, size = [], 0
            buf.append(atom)
            size += len(atom) + 1
        if buf:
            self.add(title, source, "ppt", "\n".join(buf), category)
        log(f"  PPT {title}: {len(atoms)} atoms")

    def build_pdf(self, path: Path) -> None:
        title = path.stem
        source = relative_to(path, self.kb)
        category = category_for(path, self.kb)
        pages = 0
        total_chars = 0
        for pno, text in extract_pdf_pages(path):
            pages += 1
            total_chars += len(text)
            # Notes PDF (42MB OneNote export) is mostly screenshots; keep
            # only pages with enough real text, otherwise OCR is needed.
            min_chars = 120 if "蓝桥杯(1)" in path.name else 50
            if len(text) < min_chars:
                continue
            for idx, ch in enumerate(chunk_prose(text, max_chars=900), 1):
                self.add(title, source, "pdf", ch, category,
                         {"page": pno, "part": idx})
        log(f"  PDF {title}: {pages} pages, {total_chars} chars")

    def build_docx(self, path: Path, ocr: bool = False) -> None:
        title = path.stem.strip()
        source = relative_to(path, self.kb)
        category = category_for(path, self.kb)
        parts, images = extract_docx_parts(path)
        text = "\n\n".join(parts)
        for idx, ch in enumerate(chunk_prose(text, max_chars=900), 1):
            self.add(title, source, "docx", ch, category, {"part": idx})
        log(f"  DOCX {title}: {len(parts)} parts, {len(text)} chars, {images} images")
        if images >= 30 and len(text) < 3000:
            self.warnings.append(f"图片型 DOCX（未 OCR）：{source}（{images} 张图）")
            if ocr:
                img_dir = self.work / "docx_images" / sha1_text(source)[:10]
                imgs = extract_docx_images(path, img_dir)
                texts = ocr_images(imgs)
                for idx, t in enumerate(texts, 1):
                    for j, ch in enumerate(chunk_prose(t, max_chars=900), 1):
                        self.add(f"{title}（OCR {idx}）", source, "exam_ocr", ch,
                                 category, {"image": idx, "part": j})
                log(f"  OCR DOCX {title}: {len(texts)}/{len(imgs)} images")

    def build_xlsx(self, path: Path) -> None:
        title = path.stem
        source = relative_to(path, self.kb)
        category = category_for(path, self.kb)
        for idx, part in enumerate(extract_xlsx_parts(path), 1):
            for j, ch in enumerate(chunk_prose(part, max_chars=900), 1):
                self.add(title, source, "xlsx", ch, category, {"sheet_part": idx, "part": j})
        log(f"  XLSX {title}")

    # -- code --------------------------------------------------------------
    def build_code_file(self, path: Path, project: str, source: str,
                        category: str) -> None:
        text = read_text_file(path)
        if not text:
            return
        suffix = path.suffix.lower()
        if suffix == ".ioc":
            for idx, ch in enumerate(chunk_prose(text, max_chars=900), 1):
                self.add(f"CubeMX 配置 / {path.name}", source, "ioc", ch,
                         category, {"file": path.name, "project": project, "part": idx})
            return
        chunks = chunk_code(text, file_hint=path.name)
        for idx, ch in enumerate(chunks, 1):
            func = ""
            m = re.search(r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", ch)
            if m:
                func = m.group(1)
            title = code_title(path, project)
            if func:
                title = f"{title} :: {func}()"
            self.add(title, source, "code", ch, category,
                     {"file": path.name, "project": project, "part": idx, "lang": "c"})

    def build_archives(self) -> None:
        archives = discover_archives(self.kb)
        log(f"源码压缩包：{len(archives)} 个（已去重）")
        for idx, archive in enumerate(archives, 1):
            rel_archive = relative_to(archive, self.kb)
            log(f"[{idx}/{len(archives)}] {rel_archive}")
            dest = self.work / "code" / f"{idx:03d}_{sha1_text(rel_archive)[:8]}"
            if not extract_archive_sources(archive, dest, self.seven_zip):
                continue
            files = [p for p in dest.rglob("*") if p.is_file() and is_useful_code(p)]
            log(f"  useful source files: {len(files)}")
            for f in sorted(files):
                rel_file = relative_to(f, dest)
                # project = first path component under the archive root
                first = rel_file.split("/", 1)[0]
                project = first if "/" in rel_file else archive.stem
                source = f"{rel_archive}!{rel_file}"
                self.build_code_file(f, project, source, "源码")
            if not getattr(self, "keep_work", False):
                shutil.rmtree(dest, ignore_errors=True)

    # -- local board facts -------------------------------------------------
    def build_local_firmware(self) -> None:
        """Index the verified BSP code from this project first.

        It is the only code that matches the verified pin map (LED/PD2,
        USART1 AF_PP, ADC PB12, TIM15_CH1 PA2), so it should outrank generic
        tutorial projects in retrieval.
        """
        roots = [ROOT / "firmware" / "Src", ROOT / "firmware" / "Inc"]
        count = 0
        for base in roots:
            if not base.is_dir():
                continue
            for p in sorted(base.rglob("*")):
                if p.suffix.lower() not in (".c", ".h") or not p.is_file():
                    continue
                rel = relative_to(p, ROOT)
                self.build_code_file(p, "本机固件", f"firmware/{rel.split('firmware/', 1)[-1]}", "本机固件")
                count += 1
        log(f"  本机固件源码：{count} 个文件")

    def build_board_facts(self) -> None:
        facts = ROOT / "docs" / "board_facts.md"
        if not facts.is_file():
            return
        text = read_text_file(facts)
        # Keep each Markdown section intact: a beginner question maps to one
        # coherent section (LED, USART, LCD, ...), not an arbitrary window.
        sections: list[tuple[str, str]] = []
        h2 = "总览"
        current = h2
        buf: list[str] = []
        for line in text.split("\n"):
            if line.startswith("## ") or line.startswith("### "):
                if buf and "\n".join(buf).strip():
                    sections.append((current, "\n".join(buf).strip()))
                if line.startswith("## "):
                    h2 = line[3:].strip()
                    current = h2
                else:
                    current = f"{h2} / {line[4:].strip()}"
                buf = [line]
            else:
                buf.append(line)
        if buf and "\n".join(buf).strip():
            sections.append((current, "\n".join(buf).strip()))
        for idx, (heading, body) in enumerate(sections, 1):
            title = f"板卡事实卡 · {heading}"
            for j, ch in enumerate(chunk_prose(body, max_chars=1100), 1):
                self.add(title, "docs/board_facts.md", "board",
                         ch, "本机实测", {"section": heading, "part": j})
        log(f"  板卡事实卡：{len(text)} chars / {len(sections)} 节")

    # -- output ------------------------------------------------------------
    def write(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / "chunks.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        manifest = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "kb": str(self.kb),
            "chunks": len(self.chunks),
            "sources": len(self.source_files),
            "chars": sum(len(c["text"]) for c in self.chunks),
            "by_kind": dict(Counter(c["kind"] for c in self.chunks)),
            "by_category": dict(Counter(c["category"] for c in self.chunks)),
            "warnings": self.warnings,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        (self.out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"写入 {path}：{manifest['chunks']} chunks / {manifest['chars']} chars")
        log(f"manifest: {self.out / 'manifest.json'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", type=Path, default=DEFAULT_KB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK)
    ap.add_argument("--no-archives", action="store_true")
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--ocr-docx", action="store_true", help="OCR image-only DOCX exam compilations")
    ap.add_argument("--seven-zip", type=Path, default=SEVEN_ZIP)
    args = ap.parse_args(argv)

    if not args.kb.is_dir():
        log(f"知识库路径不存在：{args.kb}")
        return 2
    if not args.seven_zip.is_file() and not args.no_archives:
        log(f"7-Zip 不存在：{args.seven_zip}")
        return 2
    args.work.mkdir(parents=True, exist_ok=True)
    b = Builder(args.kb, args.out, args.work, args.seven_zip)
    b.keep_work = args.keep_work
    started = time.time()

    log("== 本地板卡事实卡 ==")
    b.build_board_facts()
    log("== 本机固件源码 ==")
    b.build_local_firmware()

    log("== PPT ==")
    ppts = sorted([p for p in args.kb.rglob("*") if p.suffix.lower() in {".ppt", ".pptx"} and p.is_file()],
                  key=lambda p: len(str(p)))
    seen_ppt_hash: set[str] = set()
    for p in ppts:
        if p.name.startswith("~$"):
            continue
        h = sha1_bytes(p.read_bytes())
        if h in seen_ppt_hash:
            continue
        seen_ppt_hash.add(h)
        b.build_ppt(p)

    log("== PDF ==")
    for p in sorted(args.kb.rglob("*.pdf")):
        b.build_pdf(p)

    log("== DOCX ==")
    for p in sorted(args.kb.rglob("*.docx")):
        b.build_docx(p, ocr=args.ocr_docx)

    log("== XLSX ==")
    for p in sorted(args.kb.rglob("*.xlsx")):
        b.build_xlsx(p)

    if not args.no_archives:
        log("== 源码压缩包 ==")
        b.build_archives()

    b.write()
    log(f"完成，用时 {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
