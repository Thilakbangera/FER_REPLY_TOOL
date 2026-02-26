from __future__ import annotations

import re
from typing import List

import pdfplumber

# Keep this high so full abstracts are preserved, including multi-page abstracts.
_MAX_ABSTRACT_WORDS = 1200

_STOP_HEADINGS = re.compile(
    r"^(?:what\s+is\s+claimed|claims?|we\s+claim|claim\s*\d+|"
    r"detailed\s+description|description(?:\s+of\s+the\s+drawings?)?|"
    r"brief\s+description(?:\s+of\s+the\s+drawings?)?|"
    r"technical\s+field|field\s+of\s+the\s+invention|background(?:\s+of\s+the\s+invention)?|"
    r"summary(?:\s+of\s+the\s+invention)?|examples?|drawings?)\b",
    re.I,
)


def normalize_prior_art_label(label: str, index: int) -> str:
    raw = (label or "").strip().upper()
    if re.fullmatch(r"D\d{1,3}", raw):
        return raw
    return f"D{index}"


def clean_prior_art_text(text: str) -> str:
    t = (text or "").replace("\u00ad", "")
    t = re.sub(r"\(cid:\d+\)", "", t)
    t = re.sub(r"https?://\S+|www\.\S+", "", t, flags=re.I)
    t = re.sub(
        r"\b\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s+Espacenet\s*[–-]\s*search\s+results\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\bEspacenet\s*[–-]\s*search\s+results\b", " ", t, flags=re.I)
    t = re.sub(r"\bsearch\s+results\b", " ", t, flags=re.I)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)

    lines: List[str] = []
    for raw_line in t.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        if _is_noise_line(line):
            continue
        lines.append(line)

    paragraphs: List[str] = []
    cur: List[str] = []
    for line in lines:
        if not line:
            if cur:
                paragraphs.append(" ".join(cur).strip())
                cur = []
            continue
        cur.append(line)
    if cur:
        paragraphs.append(" ".join(cur).strip())

    cleaned = "\n\n".join(p for p in paragraphs if p)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    cleaned = _polish_abstract_tail(cleaned)
    return cleaned


def _normalize_line(line: str) -> str:
    s = (line or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" \t")


def _is_noise_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if re.search(r"\bsearch\s+results\b", s, re.I):
        return True
    if re.search(r"\bEspacenet\b", s, re.I):
        return True
    if re.search(r"https?://|www\.|espacenet\.com", s, re.I):
        return True
    if re.fullmatch(r"Page\s+\d+\s+of\s+\d+", s, re.I):
        return True
    if re.fullmatch(r"\[\d{1,4}\]", s):
        return True
    if re.fullmatch(r"\d{1,4}", s):
        return True
    if re.fullmatch(r"[A-Z]{1,3}\d{5,}[A-Z0-9]*", s):
        return True
    if re.fullmatch(r"\d{2,4}[/-]\d{2}[/-]\d{2,4}", s):
        return True
    if re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", s, re.I):
        return True
    if re.fullmatch(r"THE\s+PATENT\s+OFFICE", s, re.I):
        return True
    if re.search(r"\bDocument\s+generated\s+on\b", s, re.I):
        return True
    if len(re.findall(r"[A-Za-z]", s)) < 2 and len(s) < 8:
        return True
    return False


def _is_section_heading(line: str) -> bool:
    s = (line or "").strip(" :-")
    if not s:
        return False

    lower = s.lower()
    heading_starts = (
        "abstract",
        "technical field",
        "field of the invention",
        "background",
        "summary",
        "brief description",
        "detailed description",
        "claims",
        "what is claimed",
        "drawings",
        "examples",
    )
    if any(lower.startswith(h) for h in heading_starts):
        return True

    if len(s) <= 85 and s == s.upper():
        words = re.findall(r"[A-Za-z]+", s)
        if 1 <= len(words) <= 12:
            return True

    if re.match(r"^\d+[\.\)]\s+[A-Z][A-Za-z ]{2,80}$", s):
        return True

    return False


def _trim_words(text: str, max_words: int = _MAX_ABSTRACT_WORDS) -> str:
    raw = re.sub(r"\s+", " ", (text or "")).strip()
    words = re.findall(r"\S+", raw)
    if len(words) <= max_words:
        return raw

    cut = " ".join(words[:max_words]).strip()
    if cut.endswith((".", "!", "?")):
        return cut

    tail_words = words[max_words:max_words + 80]
    if tail_words:
        tail_probe = " ".join(tail_words).strip()
        m = re.search(r"[.!?](?:\s|$)", tail_probe)
        if m:
            return f"{cut} {tail_probe[:m.end()].strip()}".strip()

    back_cut = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    if back_cut >= int(len(cut) * 0.35):
        return cut[:back_cut + 1].strip()

    return f"{cut}."


def _polish_abstract_tail(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""

    # Remove dangling OCR residue like a trailing single character token.
    t = re.sub(r"(?:\s+[A-Za-z])+$", "", t).strip()
    if not t:
        return ""

    # If no terminal punctuation, preserve enumerated abstract tails and add a period.
    if t[-1] not in ".!?":
        # Example: "...;(210) ...;(212) ...;(214) ...;(FF) End"
        if re.search(r"\(\d{2,4}\)", t) or re.search(r";\s*\([A-Za-z0-9,]+\)\s*[A-Za-z]", t):
            return f"{t}."

        # If likely hard truncation (very short trailing token), cut to last complete sentence.
        words = re.findall(r"\b\w+\b", t)
        last_word = words[-1] if words else ""
        if len(last_word) <= 2:
            cut = max(t.rfind("."), t.rfind("!"), t.rfind("?"))
            if cut >= int(len(t) * 0.4):
                return t[:cut + 1].strip()

        return f"{t}."
    return t


def _build_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw_line in (text or "").splitlines():
        line = _normalize_line(raw_line)
        if not line:
            lines.append("")
            continue
        if _is_noise_line(line):
            continue
        lines.append(line)
    return lines


def _collect_candidate(lines: List[str], start_idx: int, inline_text: str = "") -> str:
    parts: List[str] = []
    inline = _normalize_line(inline_text)
    if inline and not _is_noise_line(inline):
        parts.append(inline)

    for i in range(start_idx, min(len(lines), start_idx + 220)):
        line = lines[i]
        if not line:
            if parts and len(" ".join(parts).split()) >= 45:
                break
            continue
        if _is_noise_line(line):
            continue
        if _STOP_HEADINGS.match(line):
            if parts:
                break
            continue
        if _is_section_heading(line) and len(parts) >= 2:
            break
        parts.append(line)
        word_count = len(" ".join(parts).split())
        if word_count >= _MAX_ABSTRACT_WORDS and re.search(r"[.!?]\s*$", " ".join(parts).strip()):
            break
        if word_count >= (_MAX_ABSTRACT_WORDS + 90):
            break

    candidate = " ".join(parts).strip()
    if not candidate:
        return ""
    return _trim_words(candidate, _MAX_ABSTRACT_WORDS)


def _extract_heading_based(lines: List[str]) -> str:
    abs_pat = re.compile(
        r"^(?:\[\d{1,3}\]\s*)?abstract(?:\s+of\s+the\s+disclosure)?\b\s*[:\-]?\s*(.*)$",
        re.I,
    )
    for i, line in enumerate(lines):
        m = abs_pat.match(line)
        if m:
            abstract = _collect_candidate(lines, i + 1, inline_text=m.group(1))
            if len(abstract.split()) >= 28:
                return abstract

        m_inline = re.search(r"\babstract\s*[:\-]\s*(.+)$", line, re.I)
        if m_inline:
            abstract = _collect_candidate(lines, i + 1, inline_text=m_inline.group(1))
            if len(abstract.split()) >= 28:
                return abstract
    return ""


def _score_paragraph(text: str) -> int:
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return -999

    words = len(t.split())
    if words < 35:
        return -999

    score = 0
    if 55 <= words <= 220:
        score += 7
    elif 35 <= words <= 320:
        score += 3
    else:
        score -= 3

    low = t.lower()
    positive = [
        "present invention",
        "relates to",
        "discloses",
        "provides",
        "method",
        "system",
        "apparatus",
        "problem",
        "solution",
    ]
    for kw in positive:
        if kw in low:
            score += 2

    score -= low.count("claim") * 3
    score -= low.count("figure") * 2
    score -= low.count("embodiment") * 1

    if re.search(r"\bwherein\b", low):
        score -= 2
    if re.search(r"\bcomprising\b", low):
        score -= 1

    return score


def _extract_best_paragraph(lines: List[str]) -> str:
    paragraphs: List[str] = []
    cur: List[str] = []

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        para = " ".join(cur).strip()
        if para:
            paragraphs.append(para)
        cur = []

    for line in lines:
        if not line:
            flush()
            continue
        if _is_section_heading(line):
            flush()
            continue
        if _is_noise_line(line):
            continue
        cur.append(line)
        if len(" ".join(cur).split()) >= 320:
            flush()
    flush()

    if not paragraphs:
        return ""

    best = max(paragraphs, key=_score_paragraph)
    if _score_paragraph(best) < 1:
        best = max(paragraphs, key=lambda p: len(p.split()))
    return _trim_words(best, _MAX_ABSTRACT_WORDS)


def extract_prior_art_abstract_from_pdf(path: str) -> str:
    page_texts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:8]:
            page_texts.append(page.extract_text() or "")

    lines = _build_lines("\n\n".join(page_texts))
    if not lines:
        return ""

    abstract = _extract_heading_based(lines)
    if not abstract:
        abstract = _extract_best_paragraph(lines)
    if not abstract:
        abstract = _trim_words(" ".join([ln for ln in lines if ln]), 160)

    return clean_prior_art_text(abstract)
