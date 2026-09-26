from pathlib import Path

from app.label_ocr import process_label_image


def process_ocr_job(image_path: str) -> dict:
    path = Path(image_path)
    try:
        return process_label_image(path.read_bytes())
    finally:
        path.unlink(missing_ok=True)