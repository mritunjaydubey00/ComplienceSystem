import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.queue import ocr_queue, redis_connection
from app.tasks import process_ocr_job

app = FastAPI(title="PharmaLedger Compliance API", version="0.1.0")

upload_dir = Path(os.getenv("OCR_UPLOAD_DIR", "/tmp/pharmaledger-ocr"))
upload_dir.mkdir(parents=True, exist_ok=True)

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("POSTGRES_USER", "pharmaledger"),
    password=os.getenv("POSTGRES_PASSWORD", "local-development-only"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    database=os.getenv("POSTGRES_DB", "pharmaledger"),
)
database_engine = create_engine(database_url, pool_pre_ping=True)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/webp"}


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis_connection.ping()
    except (SQLAlchemyError, RedisError) as error:
        raise HTTPException(status_code=503, detail="A required service is unavailable") from error
    return {"status": "ok", "database": "ok", "redis": "ok"}


@app.post("/api/ocr/jobs", status_code=202)
async def create_ocr_job(file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Upload a supported image file")

    image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 15 MB or smaller")

    try:
        await file.seek(0)
        with Image.open(file.file) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid image") from error

    suffix = Image.registered_extensions().get(f".{image_format.lower()}", ".img")
    image_path = upload_dir / f"{uuid4().hex}{suffix}"
    image_path.write_bytes(image_bytes)

    try:
        job = ocr_queue.enqueue(process_ocr_job, str(image_path), job_timeout=300)
    except RedisError as error:
        image_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="OCR queue is unavailable") from error

    return {"job_id": job.id, "status": "queued"}


@app.get("/api/ocr/jobs/{job_id}")
def get_ocr_job(job_id: str) -> dict[str, object]:
    try:
        job = Job.fetch(job_id, connection=redis_connection)
        status = job.get_status(refresh=True)
    except NoSuchJobError as error:
        raise HTTPException(status_code=404, detail="OCR job not found") from error
    except RedisError as error:
        raise HTTPException(status_code=503, detail="OCR queue is unavailable") from error

    response: dict[str, object] = {"job_id": job.id, "status": status.value}
    if status.value == "finished":
        response["result"] = job.result
    elif status.value == "failed":
        response["error"] = "OCR processing failed"
    return response