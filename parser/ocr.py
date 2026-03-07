from paddleocr import PaddleOCR
import cv2

ocr = PaddleOCR(use_angle_cls=True, lang="en", enable_mkldnn=False)

def extract_ocr(image_path):

    result = ocr.ocr(image_path)

    lines = []

    for bbox, text in zip(result[0]['dt_polys'], result[0]['rec_texts']):

        lines.append({
            "text": text,
            "bbox": bbox
        })

    return lines