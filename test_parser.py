import argparse
from parser.ocr import extract_ocr
from parser.layout import group_lines
from parser.extractor import extract_receipt_data


def parse_receipt(image):

    ocr_results = extract_ocr(image)

    lines = group_lines(ocr_results)

    data = extract_receipt_data(lines)

    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse a receipt image.")
    parser.add_argument("image", nargs="?", default="receipt.jpg", help="Path to the image")
    parser.add_argument("-p", action="store_true", help="Dummy argument for compatibility")
    args = parser.parse_args()

    result = parse_receipt(args.image)

    print(result)