from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np
from paddleocr import PaddleOCR

MIN_WIDTH = 640
MIN_HEIGHT = 480
MIN_BLUR_SCORE = 100.0


@lru_cache(maxsize=1)
def _get_ocr_engine() -> PaddleOCR:
    return PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _read_image(image: bytes | bytearray | np.ndarray) -> np.ndarray:
    if isinstance(image, np.ndarray):
        decoded = image
    else:
        encoded = np.frombuffer(image, dtype=np.uint8)
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    if decoded is None or decoded.size == 0:
        raise ValueError("Input is not a readable image")
    if decoded.ndim == 2:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_GRAY2BGR)
    elif decoded.shape[2] == 4:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGRA2BGR)
    return decoded


def _quality_report(image: np.ndarray) -> dict[str, Any]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    resolution_ok = width >= MIN_WIDTH and height >= MIN_HEIGHT
    is_blurry = blur_score < MIN_BLUR_SCORE
    warnings = []

    if not resolution_ok:
        warnings.append(
            f"Image resolution is {width}x{height}; at least "
            f"{MIN_WIDTH}x{MIN_HEIGHT} is recommended."
        )
    if is_blurry:
        warnings.append("Image may be blurry; retake it with the label in focus.")

    return {
        "width": width,
        "height": height,
        "resolution_ok": resolution_ok,
        "blur_score": round(blur_score, 2),
        "is_blurry": is_blurry,
        "warnings": warnings,
    }


def _order_corners(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def _correct_perspective(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), dtype=np.uint8), iterations=1)
    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    min_area = width * height * 0.12
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) == 4 and cv2.contourArea(polygon) >= min_area:
            candidates.append((cv2.contourArea(polygon), polygon.reshape(4, 2)))

    if not candidates:
        return image, None

    corners = _order_corners(max(candidates, key=lambda candidate: candidate[0])[1])
    top_left, top_right, bottom_right, bottom_left = corners
    target_width = max(
        int(np.linalg.norm(bottom_right - bottom_left)),
        int(np.linalg.norm(top_right - top_left)),
    )
    target_height = max(
        int(np.linalg.norm(top_right - bottom_right)),
        int(np.linalg.norm(top_left - bottom_left)),
    )
    if target_width < 2 or target_height < 2:
        return image, None

    target = np.array(
        [
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, target)
    corrected = cv2.warpPerspective(image, transform, (target_width, target_height))
    return corrected, transform


def _enhance_contrast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    enhanced_lightness = cv2.createCLAHE(
        clipLimit=2.0, tileGridSize=(8, 8)
    ).apply(lightness)
    enhanced = cv2.merge((enhanced_lightness, channel_a, channel_b))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def _result_data(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        data = result
    else:
        data = getattr(result, "json", {})
        if callable(data):
            data = data()
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return data["res"]
    return data if isinstance(data, dict) else {}


def _run_ocr(engine: Any, image: np.ndarray) -> list[dict[str, Any]]:
    if hasattr(engine, "predict"):
        predictions = engine.predict(input=image)
    else:
        predictions = engine.ocr(image, cls=True)

    items: list[dict[str, Any]] = []
    for prediction in predictions or []:
        data = _result_data(prediction)
        polygons = data.get("dt_polys")
        if polygons is None:
            polygons = data.get("textline_polys")
        if polygons is None:
            polygons = data.get("rec_polys")
        texts = data.get("rec_texts")
        if texts is None:
            texts = data.get("textline_rec_texts")
        scores = data.get("rec_scores")
        if scores is None:
            scores = data.get("textline_rec_scores")

        if polygons is not None and texts is not None:
            if scores is None:
                scores = [0.0] * len(texts)
            for polygon, text, score in zip(polygons, texts, scores):
                text = str(text).strip()
                if text:
                    items.append(
                        {
                            "text": text,
                            "confidence": float(score),
                            "bbox": np.asarray(polygon, dtype=np.float32).tolist(),
                        }
                    )
            continue

        legacy_lines = prediction
        while (
            isinstance(legacy_lines, list)
            and len(legacy_lines) == 1
            and isinstance(legacy_lines[0], list)
            and (not legacy_lines[0] or len(legacy_lines[0][0]) == 2)
        ):
            legacy_lines = legacy_lines[0]
        for line in legacy_lines or []:
            if (
                isinstance(line, (list, tuple))
                and len(line) >= 2
                and isinstance(line[1], (list, tuple))
                and len(line[1]) == 2
            ):
                text, score = line[1]
                text = str(text).strip()
                if text:
                    items.append(
                        {
                            "text": text,
                            "confidence": float(score),
                            "bbox": np.asarray(line[0], dtype=np.float32).tolist(),
                        }
                    )
    return items


def _map_boxes_to_source(
    items: list[dict[str, Any]], transform: np.ndarray | None
) -> None:
    if transform is None:
        return

    inverse = np.linalg.inv(transform)
    for item in items:
        points = np.asarray(item["bbox"], dtype=np.float32).reshape(-1, 1, 2)
        item["bbox"] = cv2.perspectiveTransform(points, inverse).reshape(-1, 2).tolist()


def process_label_image(
    image: bytes | bytearray | np.ndarray,
    ocr_engine: Any | None = None,
) -> dict[str, Any]:
    """Check and preprocess a product label image, then return OCR text and polygons.

    Bounding-box coordinates are returned in the original image's pixel space.
    Low quality is reported as warnings; OCR is still attempted so callers can
    decide whether to accept or request a retake.
    """
    source = _read_image(image)
    quality = _quality_report(source)
    prepared, transform = _correct_perspective(source)
    prepared = _enhance_contrast(prepared)
    items = _run_ocr(ocr_engine or _get_ocr_engine(), prepared)
    _map_boxes_to_source(items, transform)

    return {
        "text": "\n".join(item["text"] for item in items),
        "items": items,
        "quality": quality,
        "preprocessing": {
            "perspective_corrected": transform is not None,
            "contrast_enhanced": True,
            "bbox_coordinate_space": "original_image_pixels",
        },
    }