# PharmaLedger Compliance Inspection

Docker Compose scaffold for the existing React inspection UI and a FastAPI service with PostgreSQL, Redis, and a separate asynchronous OCR worker.

## Project Structure

```text
.
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py       # Health and OCR job API
│       ├── label_ocr.py  # Quality checks, image correction, and PaddleOCR
│       ├── queue.py      # Redis connection and RQ queue
│       ├── tasks.py      # RQ task wrapper for label OCR
│       └── worker.py     # RQ worker process
├── backend/tests/
│   └── test_label_ocr.py
└── complience-system/
	├── Dockerfile        # Vite build served by Nginx
	├── nginx.conf        # SPA fallback and /api reverse proxy
	└── src/              # Existing React application
```

## Start Locally

Copy `.env.example` to `.env`, then set a local `POSTGRES_PASSWORD`. From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8080`. The frontend container serves the built React app and forwards `/api/*` to FastAPI. PostgreSQL, Redis, and OCR uploads are stored in named Docker volumes. The API is available at `http://localhost:8080/api/health` through the frontend proxy.

## OCR API

- `POST /api/ocr/jobs` accepts a multipart `file` upload (JPEG, PNG, TIFF, or WebP; up to 15 MB) and returns an RQ job ID.
- `GET /api/ocr/jobs/{job_id}` returns the job status and, when complete, extracted text.
- `GET /api/health` checks PostgreSQL and Redis connectivity.

The `worker` service runs PaddleOCR outside the API request process. `backend/app/label_ocr.py` checks blur and resolution, attempts quadrilateral perspective correction, enhances local contrast with CLAHE, and returns recognized text with confidence scores and polygon boxes mapped to original image pixels. Quality issues are returned as warnings; OCR still runs so the caller can decide whether to request a retake. Uploads are temporarily shared between API and worker containers and removed after processing. This scaffold does not yet persist inspections or OCR results in PostgreSQL, and the current React capture screen still keeps its photos in browser storage; connecting those records to the API is a separate application integration step.

Backend unit tests use the standard library `unittest` runner: `python -m unittest discover -s backend/tests` from the repository root.

For deployment, provide secrets through the platform's secret manager, terminate TLS at a trusted ingress, and add authentication/authorization and retention policies before accepting real compliance evidence.
