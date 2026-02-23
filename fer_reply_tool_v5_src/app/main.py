from __future__ import annotations

import io
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.fer_parser import (
    parse_fer_pdf, to_dict, read_pdf_text,
    extract_detailed_observations_block,
    extract_formal_requirements_block,
    extract_formal_requirements_rows_from_pdf,
    extract_title_from_cs_pdf,
    extract_applicant_from_cs_pdf,
    extract_cs_background_and_summary,
)
from app.core.reply_generator import generate_reply_docx
from app.core.claims_parser import extract_amended_claims_from_pdf

app = FastAPI(title="FER Reply Generator")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://lextriatech.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,   # IMPORTANT (no cookies needed here)
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/parse_fer")
async def parse_fer(fer_pdf: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await fer_pdf.read())
        tmp_path = tmp.name
    try:
        return JSONResponse(to_dict(parse_fer_pdf(tmp_path)))
    finally:
        try: os.remove(tmp_path)
        except: pass


@app.post("/api/generate_reply")
async def generate_reply(
    fer_pdf: UploadFile = File(...),
    cs_pdf: UploadFile = File(...),                      # Complete Specification PDF (required)
    amended_claims_pdf: Optional[UploadFile] = File(None),  # Amended Claims PDF (required)
    title: str = Form(""),  # kept for backward compatibility; CS title is authoritative
    agent: Optional[str] = Form(None),
    office_address: str = Form("THE PATENT OFFICE\nI.P.O BUILDING\nG.S.T.Road, Guindy\nChennai - [PIN]"),
    dx_range: str = Form("D1-Dn"),
    dx_disclosed_features: str = Form(""),
):
    fer_path = cs_path = claims_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await fer_pdf.read())
            fer_path = tmp.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await cs_pdf.read())
            cs_path = tmp.name

        if amended_claims_pdf:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(await amended_claims_pdf.read())
                claims_path = tmp.name

        fer = parse_fer_pdf(fer_path)
        fer_raw = read_pdf_text(fer_path)
        detailed_obs = extract_detailed_observations_block(fer_raw)
        formal_reqs  = extract_formal_requirements_block(fer_raw)
        formal_rows = extract_formal_requirements_rows_from_pdf(fer_path)

        # Title must come from CS (cover sheet).
        cs_title = extract_title_from_cs_pdf(cs_path)
        if not cs_title:
            cs_title = fer.title or ""

        # Applicant must come from CS when available.
        cs_applicant = extract_applicant_from_cs_pdf(cs_path)
        if cs_applicant:
            fer.applicant = cs_applicant

        cs_background, cs_summary = extract_cs_background_and_summary(cs_path)

        # Claims: PDF only (no text fallback)
        claims_text = ""
        if claims_path:
            claims_text = extract_amended_claims_from_pdf(claims_path)

        doc = generate_reply_docx(
            fer=fer, cs_title=cs_title, amended_claims=claims_text,
            detailed_obs_text=detailed_obs, formal_reqs_text=formal_reqs,
            agent=agent, office_address=office_address,
            dx_range=dx_range, dx_disclosed_features=dx_disclosed_features,
            formal_reqs_rows=formal_rows,
            cs_background_text=cs_background,
            cs_summary_text=cs_summary,
        )

        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        filename = f"FER_Reply_Draft_{fer.application_no or 'UNKNOWN'}.docx"
        return StreamingResponse(bio,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    finally:
        for p in [fer_path, cs_path, claims_path]:
            if p:
                try: os.remove(p)
                except: pass
