from __future__ import annotations

import io
import json
import os
import tempfile
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.fer_parser import (
    parse_fer_pdf, to_dict, read_pdf_text,
    extract_detailed_observations_block,
    extract_formal_requirements_block,
    extract_formal_requirements_rows_from_pdf,
    extract_title_from_cs_pdf,
    extract_title_from_cs_docx,
    extract_applicant_from_cs_pdf,
    extract_applicant_from_cs_docx,
    extract_cs_background_and_summary,
    extract_cs_background_and_summary_from_docx,
    extract_cs_technical_effect,
    extract_cs_technical_effect_from_docx,
)
from app.core.reply_generator import generate_reply_docx
from app.core.claims_parser import extract_amended_claims_from_pdf, extract_amended_claims_from_docx
from app.core.prior_art_parser import (
    clean_prior_art_text,
    extract_prior_art_abstract_from_pdf,
    extract_prior_art_abstract_from_docx,
    is_scanned_prior_art_pdf,
    normalize_prior_art_label,
)

app = FastAPI(title="FER Reply Generator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


def _safe_json_list(raw: str) -> List[Dict]:
    if not (raw or "").strip():
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _safe_file_suffix(name: str, fallback: str = ".bin") -> str:
    base = (name or "").strip()
    _, ext = os.path.splitext(base)
    ext = (ext or "").lower()
    if _is_safe_ext(ext):
        return ext
    return fallback


def _is_safe_ext(ext: str) -> bool:
    return bool(ext) and len(ext) <= 8 and ext.startswith(".") and ext[1:].isalnum()


def _ensure_supported_doc_ext(name: str, field_name: str) -> str:
    ext = _safe_file_suffix(name or "", fallback="")
    if ext in {".pdf", ".docx"}:
        return ext
    raise HTTPException(
        status_code=422,
        detail=f"{field_name} supports only PDF or DOCX files.",
    )


async def _save_upload_to_temp(upload: UploadFile, suffix: str = ".bin") -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await upload.read())
        return tmp.name


def _normalize_manual_prior_art_entries(raw_entries: List[Dict]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, row in enumerate(raw_entries, 1):
        label = normalize_prior_art_label(str(row.get("label", "")), i)
        abstract = clean_prior_art_text(str(row.get("abstract", "")))
        diagram = clean_prior_art_text(str(row.get("diagram", "")))
        if not abstract and not diagram:
            continue
        out.append(
            {
                "label": label,
                "abstract": abstract,
                "diagram": diagram,
                "source_name": clean_prior_art_text(str(row.get("source_name", ""))),
            }
        )
    return out


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
    cs_pdf: UploadFile = File(...),                      # Complete Specification PDF/DOCX (required)
    amended_claims_pdf: Optional[UploadFile] = File(None),  # Amended Claims PDF/DOCX (required)
    prior_art_pdfs: Optional[List[UploadFile]] = File(None),  # Prior-art PDF/DOCX uploads
    prior_art_diagrams: Optional[List[UploadFile]] = File(None),
    technical_effect_images: Optional[List[UploadFile]] = File(None),
    title: str = Form(""),  # kept for backward compatibility; CS title is authoritative
    agent: Optional[str] = Form(None),
    office_address: str = Form("THE PATENT OFFICE\nI.P.O BUILDING\nG.S.T.Road, Guindy\nChennai - [PIN]"),
    dx_range: str = Form("D1-Dn"),
    dx_disclosed_features: str = Form(""),
    prior_art_mode: str = Form("pdf"),
    prior_art_input_mode: str = Form(""),
    prior_art_manual_json: str = Form(""),
    prior_arts_json: str = Form(""),
    prior_art_pdf_meta_json: str = Form(""),
    prior_arts_meta_json: str = Form(""),
):
    fer_path = cs_path = claims_path = None
    prior_art_paths: List[str] = []
    prior_art_diagram_paths: List[str] = []
    technical_effect_image_paths: List[str] = []
    try:
        fer_path = await _save_upload_to_temp(fer_pdf, suffix=".pdf")
        cs_ext = _ensure_supported_doc_ext(cs_pdf.filename or "", "CS document")
        cs_path = await _save_upload_to_temp(cs_pdf, suffix=cs_ext)

        claims_ext = ""
        if amended_claims_pdf:
            claims_ext = _ensure_supported_doc_ext(amended_claims_pdf.filename or "", "Amended Claims document")
            claims_path = await _save_upload_to_temp(amended_claims_pdf, suffix=claims_ext)

        fer = parse_fer_pdf(fer_path)
        fer_raw = read_pdf_text(fer_path)
        detailed_obs = extract_detailed_observations_block(fer_raw)
        formal_reqs  = extract_formal_requirements_block(fer_raw)
        formal_rows = extract_formal_requirements_rows_from_pdf(fer_path)

        # Title must come from CS (cover sheet).
        if cs_ext == ".pdf":
            cs_title = extract_title_from_cs_pdf(cs_path)
        else:
            cs_title = extract_title_from_cs_docx(cs_path)
        if not cs_title:
            cs_title = fer.title or ""

        # Applicant must come from CS when available.
        if cs_ext == ".pdf":
            cs_applicant = extract_applicant_from_cs_pdf(cs_path)
        else:
            cs_applicant = extract_applicant_from_cs_docx(cs_path)
        if cs_applicant:
            fer.applicant = cs_applicant

        if cs_ext == ".pdf":
            cs_background, cs_summary = extract_cs_background_and_summary(cs_path)
            cs_technical_effect = extract_cs_technical_effect(cs_path)
        else:
            cs_background, cs_summary = extract_cs_background_and_summary_from_docx(cs_path)
            cs_technical_effect = extract_cs_technical_effect_from_docx(cs_path)

        # Claims: PDF only (no text fallback)
        claims_text = ""
        if claims_path:
            if claims_ext == ".pdf":
                claims_text = extract_amended_claims_from_pdf(claims_path)
            else:
                claims_text = extract_amended_claims_from_docx(claims_path)

        prior_art_entries: List[Dict[str, str]] = []
        mode = (prior_art_input_mode or prior_art_mode or "pdf").strip().lower()

        manual_json_raw = prior_arts_json if (prior_arts_json or "").strip() else prior_art_manual_json
        pdf_meta_json_raw = prior_arts_meta_json if (prior_arts_meta_json or "").strip() else prior_art_pdf_meta_json

        pdf_meta_rows = _safe_json_list(pdf_meta_json_raw)
        meta_by_upload_name: Dict[str, Dict] = {}
        for row in pdf_meta_rows:
            upload_name = clean_prior_art_text(str(row.get("upload_name", "")))
            if upload_name and upload_name not in meta_by_upload_name:
                meta_by_upload_name[upload_name] = row

        if mode == "text":
            manual_rows = _safe_json_list(manual_json_raw)
            dia_iter = iter(list(prior_art_diagrams or []))
            for i, row in enumerate(manual_rows, 1):
                label = normalize_prior_art_label(str(row.get("label", "")), i)
                abstract = clean_prior_art_text(str(row.get("abstract", "")))
                diagram_text = clean_prior_art_text(str(row.get("diagram", "")))
                diagram_path = ""

                has_diagram = bool(row.get("has_diagram", False)) or bool(diagram_text)
                diagram_name = ""
                if has_diagram:
                    dimg = next(dia_iter, None)
                    if dimg is not None and (dimg.filename or "").strip():
                        diagram_name = clean_prior_art_text(dimg.filename)
                        ext = _safe_file_suffix(dimg.filename, fallback=".png")
                        diagram_path = await _save_upload_to_temp(dimg, suffix=ext)
                        prior_art_diagram_paths.append(diagram_path)

                if not diagram_text and has_diagram:
                    diagram_text = f"Diagram provided ({diagram_name})" if diagram_name else "Diagram provided"

                if not abstract and not diagram_text and not diagram_path:
                    continue
                prior_art_entries.append(
                    {
                        "label": label,
                        "abstract": abstract,
                        "diagram": diagram_text,
                        "diagram_path": diagram_path,
                        "source_name": clean_prior_art_text(str(row.get("source_name", ""))),
                    }
                )
        else:
            pdf_list = list(prior_art_pdfs or [])
            dia_list = list(prior_art_diagrams or [])
            dia_iter = iter(dia_list)
            total_rows = max(len(pdf_meta_rows), len(pdf_list), len(dia_list))
            for i in range(total_rows):
                upload = pdf_list[i] if i < len(pdf_list) else None

                row = {}
                if upload is not None:
                    row = meta_by_upload_name.get(upload.filename or "") or {}
                if not row and i < len(pdf_meta_rows):
                    row = pdf_meta_rows[i]

                label = normalize_prior_art_label(str(row.get("label", "")), i + 1)
                diagram = clean_prior_art_text(str(row.get("diagram", "")))
                diagram_path = ""
                abstract = ""
                source_name = ""

                if upload is not None:
                    source_name = clean_prior_art_text(upload.filename or "")
                    prior_ext = _ensure_supported_doc_ext(upload.filename or "", f"Prior art file {source_name or label}")
                    prior_path = await _save_upload_to_temp(upload, suffix=prior_ext)
                    prior_art_paths.append(prior_path)
                    if prior_ext == ".pdf":
                        if is_scanned_prior_art_pdf(prior_path):
                            display_name = source_name or label
                            raise HTTPException(
                                status_code=422,
                                detail=f"{display_name} is a scanned copy (image-only PDF). Please provide text copy PDF.",
                            )
                        abstract = extract_prior_art_abstract_from_pdf(prior_path)
                    else:
                        abstract = extract_prior_art_abstract_from_docx(prior_path)

                has_diagram = bool(row.get("has_diagram", False)) or bool(diagram)
                diagram_upload = next(dia_iter, None) if has_diagram else None
                if diagram_upload is None and not pdf_meta_rows and i < len(dia_list):
                    # Backward fallback when per-row metadata is absent.
                    diagram_upload = dia_list[i]

                diagram_name = clean_prior_art_text((diagram_upload.filename or "") if diagram_upload else "")
                if diagram_upload is not None and (diagram_upload.filename or "").strip():
                    ext = _safe_file_suffix(diagram_upload.filename, fallback=".png")
                    diagram_path = await _save_upload_to_temp(diagram_upload, suffix=ext)
                    prior_art_diagram_paths.append(diagram_path)
                if not diagram and has_diagram:
                    diagram = f"Diagram provided ({diagram_name})" if diagram_name else "Diagram provided"

                if not abstract and not diagram and not diagram_path:
                    continue
                prior_art_entries.append(
                    {
                        "label": label,
                        "abstract": abstract,
                        "diagram": diagram,
                        "diagram_path": diagram_path,
                        "source_name": source_name,
                    }
                )

        for img in list(technical_effect_images or []):
            if img is None or not (img.filename or "").strip():
                continue
            ext = _safe_file_suffix(img.filename, fallback=".png")
            img_path = await _save_upload_to_temp(img, suffix=ext)
            technical_effect_image_paths.append(img_path)

        doc = generate_reply_docx(
            fer=fer, cs_title=cs_title, amended_claims=claims_text,
            detailed_obs_text=detailed_obs, formal_reqs_text=formal_reqs,
            agent=agent, office_address=office_address,
            dx_range=dx_range, dx_disclosed_features=dx_disclosed_features,
            prior_art_entries=prior_art_entries,
            formal_reqs_rows=formal_rows,
            cs_background_text=cs_background,
            cs_summary_text=cs_summary,
            cs_technical_effect_text=cs_technical_effect,
            technical_effect_image_paths=technical_effect_image_paths,
        )

        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        filename = f"FER_Reply_Draft_{fer.application_no or 'UNKNOWN'}.docx"
        return StreamingResponse(bio,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    finally:
        for p in [fer_path, cs_path, claims_path, *prior_art_paths, *prior_art_diagram_paths, *technical_effect_image_paths]:
            if p:
                try: os.remove(p)
                except: pass
