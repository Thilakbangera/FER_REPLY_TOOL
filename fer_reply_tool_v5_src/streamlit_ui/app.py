import requests
import streamlit as st

st.set_page_config(page_title="FER Reply Generator", page_icon="DOC", layout="wide")

BACKEND = st.sidebar.text_input("Backend URL", "http://127.0.0.1:8000")

st.title("FER Reply Generator")
st.caption("Upload FER PDF + CS PDF + Amended Claims PDF to auto-generate the reply DOCX with objections pre-filled.")

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### 1) FER PDF *(required)*")
    fer_file = st.file_uploader("FER PDF", type=["pdf"], key="fer_pdf")

    st.markdown("### 2) Complete Specification PDF *(required for title and applicant)*")
    cs_file = st.file_uploader("CS PDF", type=["pdf"], key="cs_pdf")

    st.markdown("### 3) Optional inputs")
    agent = st.text_input("Patent Agent name")
    dx_range = st.text_input("DX range (e.g., D1, D2, D3)", "D1-Dn")
    dx_disclosed_features = st.text_area(
        "D1-Dn disclosed features (right-side table text)",
        value="",
        height=120,
    )
    office_address = st.text_area(
        "Patent Office address",
        value="THE PATENT OFFICE\nI.P.O BUILDING\nG.S.T.Road, Guindy\nChennai - [PIN]",
        height=120,
    )

with col_right:
    st.markdown("### 4) Amended Claims PDF *(required)*")
    claims_pdf = st.file_uploader(
        "Upload the Amended Claims PDF - claims are extracted automatically",
        type=["pdf"],
        key="claims_pdf",
    )
    if claims_pdf:
        st.success("Claims PDF uploaded - will be extracted automatically")
    else:
        st.info("Upload the Amended Claims PDF to populate the claims section.")

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
            st.error(f"Error {r.status_code}: {r.text}")
        else:
            st.json(r.json())

with col2:
    generate_disabled = (fer_file is None) or (cs_file is None) or (claims_pdf is None)
    if generate_disabled and fer_file is not None:
        st.warning("Please upload CS PDF and Amended Claims PDF to generate the reply.")

    if st.button("Generate FER Reply DOCX", disabled=generate_disabled, type="primary"):
        with st.spinner("Generating DOCX..."):
            files = {
                "fer_pdf": ("fer.pdf", fer_file.getvalue(), "application/pdf"),
                "cs_pdf": ("cs.pdf", cs_file.getvalue(), "application/pdf"),
                "amended_claims_pdf": ("claims.pdf", claims_pdf.getvalue(), "application/pdf"),
            }
            data = {
                "title": "",
                "agent": agent or "",
                "office_address": office_address,
                "dx_range": dx_range,
                "dx_disclosed_features": dx_disclosed_features,
            }
            r = requests.post(f"{BACKEND}/api/generate_reply", files=files, data=data)

        if r.status_code != 200:
            st.error(f"Error {r.status_code}: {r.text}")
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
2. Upload **CS PDF** (required) - title and applicant are extracted from CS
3. Upload **Amended Claims PDF** (required) - claims are extracted automatically
4. Optionally fill Patent Agent name, DX range/disclosed features, and patent office address
5. Click **Generate FER Reply DOCX**
6. Open in Word and fill the red placeholders for each objection reply
"""
)
