import unittest

import numpy as np

from app.label_ocr import _quality_report, process_label_image


class FakePaddleOCR:
    def predict(self, input):
        return [
            {
                "res": {
                    "dt_polys": [
                        np.array([[10, 10], [90, 10], [90, 30], [10, 30]])
                    ],
                    "rec_texts": ["LOT 123"],
                    "rec_scores": [0.97],
                }
            }
        ]


class LabelOCRTests(unittest.TestCase):
    def test_quality_report_flags_small_blurry_images(self):
        image = np.zeros((100, 120, 3), dtype=np.uint8)

        quality = _quality_report(image)

        self.assertFalse(quality["resolution_ok"])
        self.assertTrue(quality["is_blurry"])
        self.assertEqual(len(quality["warnings"]), 2)

    def test_process_returns_text_confidence_and_source_coordinates(self):
        image = np.zeros((600, 800, 3), dtype=np.uint8)

        result = process_label_image(image, ocr_engine=FakePaddleOCR())

        self.assertEqual(result["text"], "LOT 123")
        self.assertEqual(result["items"][0]["confidence"], 0.97)
        self.assertEqual(result["items"][0]["bbox"][0], [10.0, 10.0])
        self.assertTrue(result["preprocessing"]["contrast_enhanced"])
        self.assertEqual(
            result["preprocessing"]["bbox_coordinate_space"],
            "original_image_pixels",
        )

    def test_rejects_undecodable_image_bytes(self):
        with self.assertRaises(ValueError):
            process_label_image(b"not an image", ocr_engine=FakePaddleOCR())


if __name__ == "__main__":
    unittest.main()