from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from geometry import normalize_request, SurfaceRequest


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-mini"
TIMEOUT_SECONDS = 30

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "surface_type": {
            "type": "string",
            "enum": [
                "gyroid",
                "schwarz_p",
                "diamond",
                "neovius",
                "lidinoid",
                "custom_explicit",
                "custom_implicit",
            ],
        },
        "periods": {"type": "integer", "minimum": 1, "maximum": 4},
        "resolution": {"type": "integer", "minimum": 32, "maximum": 72},
        "iso_level": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "expression": {"type": "string"},
        "coloring": {"type": "string", "enum": ["normal", "height", "radial", "curvature", "none"]},
        "colormap": {"type": "string", "enum": ["viridis", "plasma", "coolwarm", "rainbow"]},
    },
    "required": [
        "surface_type",
        "periods",
        "resolution",
        "iso_level",
        "expression",
        "coloring",
        "colormap",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
Extract parameters for a 3D implicit geometry generator.

Return defaults when the user does not specify a value:
- surface_type: gyroid
- periods: 2
- resolution: 48
- iso_level: 0.0
- expression: empty string unless a custom surface is requested
- coloring: normal
- colormap: viridis

Surface choices:
- gyroid, schwarz_p, diamond, neovius, lidinoid
- custom_explicit for z = f(x, y)
- custom_implicit for F(x, y, z) = 0

For custom_explicit, expression must be only the right-hand side, like sin(x) * cos(y).
For custom_implicit, expression must be only the left-hand side, like x**2 + y**2 + z**2 - 4.
Use Python math syntax. Convert caret exponent notation to **.

Map qualitative resolution terms this way:
- low: 32
- medium: 48
- high: 72

Coloring choices:
- normal, height, radial, curvature, none

Colormap choices:
- viridis, plasma, coolwarm, rainbow
""".strip()


class ExtractionError(RuntimeError):
    pass


def extract_surface_request(user_message: str) -> SurfaceRequest:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ExtractionError("OPENAI_API_KEY is required for this example.")

    payload = {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "surface_request",
                "strict": True,
                "schema": EXTRACTION_SCHEMA,
            }
        },
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise ExtractionError(f"OpenAI request failed with HTTP {exc.code}: {details[:300]}") from exc
    except Exception as exc:
        raise ExtractionError(f"OpenAI request failed: {exc}") from exc

    text = _extract_output_text(body)
    if not text:
        raise ExtractionError("OpenAI response did not contain structured output text.")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("OpenAI response was not valid JSON.") from exc

    return normalize_request(raw)


def _extract_output_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"].strip()

    for item in body.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                return content["text"].strip()

    return ""
