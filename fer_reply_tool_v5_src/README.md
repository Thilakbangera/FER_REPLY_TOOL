# FER Reply Generator (Template-Locked, Option B)

This project generates a **FER Reply draft** from:
- FER (PDF)
- CS Title (text)
- Amended Claims (PDF recommended; text fallback)

It follows a **strict fixed section order** and **leaves placeholders** for the core "reply/argument" part (Option B).
You can edit the generated DOCX in Word.

## Quick Start (VS Code)

### 1) Create venv + install
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2) Run backend (FastAPI)
```bash
uvicorn app.main:app --reload --port 8000
```

### 3) Run UI (Streamlit)
Open a new terminal:
```bash
streamlit run streamlit_ui/app.py
```

UI will call backend at `http://127.0.0.1:8000`.

## API

### POST /api/parse_fer
Multipart form-data:
- `fer_pdf` : PDF file

Returns: normalized JSON containing metadata + objections.

### POST /api/generate_reply
Multipart form-data:
- `fer_pdf` : PDF file
- `cs_pdf` : PDF file (required; title + applicant are extracted from CS)
- `amended_claims_pdf` : PDF file (preferred)
- Optional:
  - `title` (string, ignored when CS is present)
  - `agent` (string)
  - `office_address` (multiline string)
  - `dx_range` (string, e.g. `D1, D2, D3`)
  - `dx_disclosed_features` (multiline string for right-side comparison table)

Returns: generated `.docx` as a file download.

## Notes
- This version intentionally does **NOT** write substantive arguments.
- It auto-inserts placeholders like `[INSERT REPLY TO OBJECTION 1 HERE]`.
- It extracts objection headings + cited documents from the FER wherever possible.

## Sample Inputs
See `sample_inputs/` for example files (if present).
