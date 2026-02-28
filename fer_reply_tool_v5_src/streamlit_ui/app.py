import json

import requests
import streamlit as st

st.set_page_config(page_title="FER Reply Generator", page_icon="DOC", layout="wide")

BACKEND = st.sidebar.text_input("Backend URL", "https://fer-reply-tool.onrender.com")
BACKEND = BACKEND.strip().rstrip("/")
if BACKEND and not BACKEND.startswith(("http://", "https://")):
    BACKEND = "https://" + BACKEND

st.title("FER Reply Generator")
st.caption("Upload FER PDF + CS/Claims documents (PDF or DOCX) to auto-generate the reply DOCX with objections pre-filled.")

col_left, col_right = st.columns(2)

if "prior_art_count" not in st.session_state:
    st.session_state.prior_art_count = 1

prior_art_input_mode = "pdf"
prior_arts_entries = []
prior_art_pdf_uploads = []
prior_art_diagram_uploads = []
technical_effect_image_uploads = []
prior_art_complete = True


def _error_message(resp: requests.Response) -> str:
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            detail = payload.get("detail", "")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text or f"Request failed with status {resp.status_code}"


def _upload_tuple(upload, fallback_name: str, fallback_mime: str):
    name = (getattr(upload, "name", "") or fallback_name).strip() or fallback_name
    mime = (getattr(upload, "type", "") or "").strip()
    if not mime:
        if name.lower().endswith(".docx"):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif name.lower().endswith(".pdf"):
            mime = "application/pdf"
        else:
            mime = fallback_mime
    return (name, upload.getvalue(), mime)


with col_left:
    st.markdown("### 1) FER PDF *(required)*")
    fer_file = st.file_uploader("FER PDF", type=["pdf"], key="fer_pdf")

    st.markdown("### 2) Complete Specification PDF/Word *(required for title and applicant)*")
    cs_file = st.file_uploader("CS Document", type=["pdf", "docx"], key="cs_pdf")

    st.markdown("### 3) Optional inputs")
    agent = st.text_input("Patent Agent name")
    dx_range = st.text_input("DX range (e.g., D1, D2, D3)", "D1-Dn")
    dx_disclosed_features = st.text_area(
        "D1-Dn disclosed features (right-side table text)",
        value="",
        height=120,
    )
    st.markdown("### 3.1) Prior Arts (D1-Dn)")
    prior_art_input_mode_label = st.selectbox(
        "Prior Art Input Mode",
        options=["From Prior-Art Document (PDF/Word, Auto Abstract Extraction)", "Manual Abstract Text"],
        index=0,
        key="prior_art_mode",
        help="Choose how prior arts are provided.",
    )
    prior_art_input_mode = "pdf" if prior_art_input_mode_label.startswith("From Prior-Art Document") else "text"

    if st.button("+ Add Prior Art", use_container_width=True, key="add_prior_art"):
        st.session_state.prior_art_count += 1
        st.rerun()

    for idx in range(max(1, st.session_state.prior_art_count)):
        default_label = f"D{idx + 1}"
        st.markdown(f"#### {default_label}")

        label = st.text_input(
            f"{default_label} Label",
            value=default_label,
            key=f"prior_art_label_{idx}",
        ).strip() or default_label

        abstract = ""
        prior_pdf = None
        if prior_art_input_mode == "pdf":
            prior_pdf = st.file_uploader(
                f"{default_label} Prior Art Document",
                type=["pdf", "docx"],
                key=f"prior_art_{idx}_pdf",
                help=f"Upload prior-art PDF/DOCX for {default_label}",
            )
            if prior_pdf is None:
                prior_art_complete = False
        else:
            abstract = st.text_area(
                f"{default_label} Abstract",
                key=f"prior_art_{idx}_abstract",
                help=f"Enter abstract for {default_label}",
                height=95,
            )
            if not abstract.strip():
                prior_art_complete = False

        diagram_img = st.file_uploader(
            f"{default_label} Diagram Image (Optional)",
            type=["png", "jpg", "jpeg"],
            key=f"prior_art_{idx}_diagram_image",
            help=f"Optional diagram image for {default_label}",
        )

        prior_art_pdf_uploads.append(prior_pdf)
        prior_art_diagram_uploads.append(diagram_img)
        prior_arts_entries.append(
            {
                "label": label,
                "abstract": abstract.strip(),
                "has_diagram": diagram_img is not None,
            }
        )

    office_address = st.text_area(
        "Patent Office address",
        value="THE PATENT OFFICE\nI.P.O BUILDING\nG.S.T.Road, Guindy\nChennai - [PIN]",
        height=120,
    )

with col_right:
    st.markdown("### 4) Amended Claims PDF/Word *(required)*")
    claims_pdf = st.file_uploader(
        "Upload the Amended Claims document - claims are extracted automatically",
        type=["pdf", "docx"],
        key="claims_pdf",
    )
    if claims_pdf:
        st.success("Amended Claims document uploaded - will be extracted automatically")
    else:
        st.info("Upload the Amended Claims PDF/DOCX to populate the claims section.")

    st.markdown("### 5) Technical Effect Images *(optional)*")
    technical_effect_image_uploads = st.file_uploader(
        "Upload image(s) to be inserted under Technical Effect",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="technical_effect_images",
    ) or []

st.divider()

col1, col2 = st.columns(2)

with col1:
    if st.button("Parse FER (Preview JSON)", disabled=fer_file is None):
        with st.spinner("Parsing FER..."):
            r = requests.post(
                f"{BACKEND}/api/parse_fer",
                files={"fer_pdf": ("fer.pdf", fer_file.getvalue(), "application/pdf")},
            )
        if r.status_code != 200:
            st.error(_error_message(r))
        else:
            st.json(r.json())

with col2:
    generate_disabled = (fer_file is None) or (cs_file is None) or (claims_pdf is None) or (not prior_art_complete)
    if generate_disabled and fer_file is not None:
        st.warning("Please complete CS document, Amended Claims document, and Prior Arts (D1-Dn) to generate the reply.")

    if st.button("Generate FER Reply DOCX", disabled=generate_disabled, type="primary"):
        with st.spinner("Generating DOCX..."):
            files = [
                ("fer_pdf", _upload_tuple(fer_file, "fer.pdf", "application/pdf")),
                ("cs_pdf", _upload_tuple(cs_file, "cs.pdf", "application/pdf")),
                ("amended_claims_pdf", _upload_tuple(claims_pdf, "claims.pdf", "application/pdf")),
            ]
            for pdf in prior_art_pdf_uploads:
                if pdf is not None:
                    files.append(("prior_art_pdfs", _upload_tuple(pdf, "prior_art.pdf", "application/pdf")))
            for img in prior_art_diagram_uploads:
                if img is not None:
                    files.append(("prior_art_diagrams", (img.name, img.getvalue(), img.type or "application/octet-stream")))
            for img in technical_effect_image_uploads:
                if img is not None:
                    files.append(("technical_effect_images", (img.name, img.getvalue(), img.type or "application/octet-stream")))

            prior_arts_meta = [
                {
                    "label": entry.get("label", ""),
                    "has_diagram": bool(entry.get("has_diagram", False)),
                }
                for entry in prior_arts_entries
            ]
            prior_arts_text_payload = [
                {
                    "label": entry.get("label", ""),
                    "abstract": entry.get("abstract", ""),
                    "has_diagram": bool(entry.get("has_diagram", False)),
                }
                for entry in prior_arts_entries
            ]
            data = {
                "title": "",
                "agent": agent or "",
                "office_address": office_address,
                "dx_range": dx_range,
                "dx_disclosed_features": dx_disclosed_features,
                "prior_art_input_mode": prior_art_input_mode,
                "prior_arts_meta_json": json.dumps(prior_arts_meta, ensure_ascii=True),
                "prior_arts_json": json.dumps(prior_arts_text_payload, ensure_ascii=True),
                # Backward-compatible aliases for the existing backend contract.
                "prior_art_mode": prior_art_input_mode,
                "prior_art_pdf_meta_json": json.dumps(prior_arts_meta, ensure_ascii=True),
                "prior_art_manual_json": json.dumps(prior_arts_text_payload, ensure_ascii=True),
            }
            r = requests.post(f"{BACKEND}/api/generate_reply", files=files, data=data)

        if r.status_code != 200:
            st.error(_error_message(r))
        else:
            st.success("Generated")
            st.download_button(
                "Download DOCX",
                data=r.content,
                file_name="FER_Reply_Draft.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

st.divider()
st.markdown(
    """
**How to use:**
1. Upload **FER PDF** (required)
2. Upload **CS PDF/DOCX** (required) - title and applicant are extracted from CS
3. Upload **Amended Claims PDF/DOCX** (required) - claims are extracted automatically
4. In **Prior Arts (D1-Dn)** choose input mode:
   - **From Prior-Art Document**: upload each D1/D2/... PDF or DOCX for abstract extraction
   - **Manual Abstract Text**: type abstract for each D1/D2/...
5. Use **+ Add Prior Art** to add D3, D4, ...
6. Optional: upload per-D **Diagram Image**
7. Optional: upload **Technical Effect Images** (inserted under Technical Effect section)
8. Optionally fill Patent Agent name, DX range/disclosed features, and patent office address
9. Click **Generate FER Reply DOCX**
10. Open in Word and fill the red placeholders for each objection reply
"""
)
