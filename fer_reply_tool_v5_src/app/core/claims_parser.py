from __future__ import annotations

import re
from typing import List
import pdfplumber


def read_pdf_text(path: str) -> str:
    chunks: List[str] = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            txt = p.extract_text() or ""
            chunks.append(txt)
    return "\n".join(chunks)


def _clean(t: str) -> str:
    t = t.replace("\u00ad", "")
    t = re.sub(r"\(cid:\d+\)", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_amended_claims_from_pdf(path: str) -> str:
    """
    Extract claim text from an amended-claims PDF.
    - Prefer start at heading variants: WE CLAIM / CLAIMS / REGARDING CLAIMS
    - Fallback to first numbered claim if heading is missing
    - End at FER reply section markers if present
    """
    t = _clean(read_pdf_text(path))
    if not t:
        return ""

    start_idx = 0
    for pat in [
        r"(?im)^\s*WE\s+CLAIM\s*:?\s*$",
        r"(?im)^\s*WE\s+CLAIM\s*:?\s*",
        r"(?im)^\s*CLAIMS?\s*:?\s*$",
        r"(?im)^\s*REGARDING\s+CLAIMS\s*:?\s*$",
        r"\bWe\s+Claim\b\s*:?",
    ]:
        m = re.search(pat, t, re.I | re.MULTILINE)
        if m:
            start_idx = m.end()
            break

    tail = t[start_idx:]
    end = len(tail)
    for ep in [
        r"\bSUBMISSION\s+TO\s+OBJECTION\b",
        r"\bFORMAL\s+REQUIREMENTS\b",
        r"\bYOURS\s+FAITHFULLY\b",
        r"\bENCLOSURE\b",
    ]:
        m2 = re.search(ep, tail, re.I)
        if m2:
            end = min(end, m2.start())

    claims_block = tail[:end].strip()

    # Claims should normally start with "1." / "1)" / "Claim 1".
    start_pat = r"(?im)^\s*(?:1[\.\):]\s+|Claim\s*1\b)"
    m3 = re.search(start_pat, claims_block)
    if m3:
        claims_block = claims_block[m3.start():].strip()
    else:
        m4 = re.search(start_pat, t)
        if m4:
            tail2 = t[m4.start():]
            end2 = len(tail2)
            for ep in [r"\bSUBMISSION\s+TO\s+OBJECTION\b", r"\bFORMAL\s+REQUIREMENTS\b", r"\bYOURS\s+FAITHFULLY\b", r"\bENCLOSURE\b"]:
                m5 = re.search(ep, tail2, re.I)
                if m5:
                    end2 = min(end2, m5.start())
            claims_block = tail2[:end2].strip()

    return claims_block
