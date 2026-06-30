# Multi-Agent Document Processing PoC

Generalized master-agent/sub-agent project for interview presentation and demo. It processes enterprise document text or selectable-text PDFs, masks sensitive data, classifies Invoice/ERP/General documents, reduces text before LLM usage, caches repeated analyses, and exports a browser report to PDF.

## Architecture

```text
User input
+- FastAPI backend
|  +- Master Agent
|  +- Sanitation Agent
|  +- Security Agent
|  +- Application Agent
|  +- Guardrails Agent
|  +- Monitoring Agent
+- Cache layer
+- Minimal web UI
```

Each agent lives in its own folder under `backend/app/agents/` to keep the system easy to extend.

## Run

### Option 1: backend serves everything

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

If the Windows Store Python shim is active, use the direct Python install:

```powershell
C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

### Option 2: run backend and frontend separately

Terminal 1, backend:

```powershell
cd C:\Users\HP\Desktop\KMP
$env:NVIDIA_NIM_API_KEY="your-key-here"
$env:NVIDIA_NIM_MODEL="meta/llama-3.1-8b-instruct"
C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Terminal 2, frontend:

```powershell
cd C:\Users\HP\Desktop\KMP
C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe -m http.server 5173 --directory frontend
```

Open `http://127.0.0.1:5173`.

When the frontend is not running on port `8000`, it automatically calls the backend at `http://127.0.0.1:8000`.

## NVIDIA NIM

The app runs with the mock provider by default. To use NVIDIA NIM, set the key in your terminal before starting the server:

```powershell
$env:NVIDIA_NIM_API_KEY="your-key-here"
$env:NVIDIA_NIM_MODEL="meta/llama-3.1-8b-instruct"
C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Optional settings:

- `NVIDIA_NIM_BASE_URL`, default `https://integrate.api.nvidia.com/v1`
- `NVIDIA_NIM_MODEL`, default `meta/llama-3.1-8b-instruct`

Do not commit real API keys. Use `.env.example` only as a template.

## API

- `GET /api/health`
- `GET /api/cache/stats`
- `POST /api/analyze`

`POST /api/analyze` accepts either:

- JSON: `{ "text": "Invoice No: INV-1 ..." }`
- Multipart form: `text` plus optional `file`

## Demo Flow

1. Load the sample document in the UI.
2. Run analysis and show cache miss.
3. Review document classification, masked PII, extracted fields, agent trace, and token tree.
4. Run the same input again and show cache hit.
5. Export the report using the PDF button.

## Sample Data

Two CSV files are included for upload demos:

- `samples/good_invoice_erp_sample.csv`: clean invoice/ERP rows.
- `samples/error_invoice_erp_sample.csv`: missing values, duplicate row, invalid dates, invalid amount, negative amount, and PII-like content.

## Tests

```powershell
python -m unittest discover -s tests
```

## Future Scope

- Add more private/internal LLM providers behind `LLMProvider`.
- Add OCR for scanned PDFs.
- Add RAG/vector database support.
- Add human-in-the-loop approval for sensitive workflows.
- Add domain agents for finance, procurement, HR, and compliance documents.
