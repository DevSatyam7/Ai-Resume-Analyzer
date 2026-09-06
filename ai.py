import os
import json
import re
import time
import urllib.request
import urllib.error


def _call_gemini_raw(prompt, models_to_try=None, temperature=0.2, json_mode=True):
    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    # Comma se split karke har key ke andar ke newlines aur spaces ko auto-stitch karna
    api_keys = ["".join(k.split()).strip("'\"") for k in raw_keys.split(",") if k.strip()]

    # Sirf genuine full-length keys rakhna
    api_keys = [k for k in api_keys if len(k) >= 35]

    if not api_keys:
        raise ValueError("No valid GEMINI_API_KEY found after cleaning.")

    # Google recommended active models (404 error resolved)
    if not models_to_try:
        models_to_try = [
            "gemini-3.6-flash",
            "gemini-2.5-flash",
            "gemini-1.5-flash"
        ]

    last_error = None

    # Multi-Key Rotation Loop
    for idx, key in enumerate(api_keys):
        for m_name in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "X-goog-api-key": key
                }
                body = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature
                    }
                }
                if json_mode:
                    body["generationConfig"]["responseMimeType"] = "application/json"

                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=25) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_text = resp_data["candidates"][0]["content"]["parts"][0]["text"].strip()

                    raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                    raw_text = re.sub(r"^
