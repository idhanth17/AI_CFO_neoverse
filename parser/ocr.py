from paddleocr import PaddleOCR
import cv2

ocr = None

def extract_ocr(image_path):
    global ocr
    if ocr is None:
        ocr = PaddleOCR(use_angle_cls=True, lang="en", enable_mkldnn=False)


    result = ocr.ocr(image_path)

    lines = []

    if not result or not result[0]:
        return lines

    for line in result[0]:
        bbox = line[0]
        text = line[1][0]
        
        lines.append({
            "text": text,
            "bbox": bbox
        })

    return lines