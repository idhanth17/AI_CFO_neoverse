def group_lines(ocr_results):

    rows = []

    for item in ocr_results:

        text = item["text"]
        box = item["bbox"]

        y = box[0][1]
        x = box[0][0]

        rows.append((y, x, text))

    rows.sort(key=lambda r: (round(r[0] / 20) * 20, r[1]))

    lines = []
    current = []
    prev_y = None

    for y, x, text in rows:

        if prev_y is None or abs(y - prev_y) < 15:

            current.append(text)

        else:

            lines.append(" ".join(current))
            current = [text]

        prev_y = y

    if current:
        lines.append(" ".join(current))

    return lines