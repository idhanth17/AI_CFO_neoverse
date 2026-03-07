from groq import Groq
import json
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_receipt_data(lines):

    text = "\n".join(lines)

    prompt = f"""
Extract receipt data and return a valid JSON object.
Crucial: Do not use arithmetic expressions (like 400+100). All values must be valid JSON strings, numbers, booleans, arrays, or null.
Fields:
vendor
date
time
phone
items
subtotal
tax
discount
total
payment_method
OCR TEXT:
{text}
Return ONLY JSON.
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content

    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except Exception as e:
        return {
            "error": "Failed to parse JSON",
            "exception": str(e),
            "raw": content
        }