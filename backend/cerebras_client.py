import base64
import json
import httpx
from backend.config import settings

CEREBRAS_API = "https://api.cerebras.ai/v1/chat/completions"
MODEL = "gemma-4-31b"

OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "terrain_type": {
            "type": "string",
            "enum": ["residential", "commercial", "industrial", "green_space", "water", "infrastructure", "unknown"],
        },
        "structures": {"type": "array", "items": {"type": "string"}},
        "landmarks": {"type": "array", "items": {"type": "string"}},
        "density": {"type": "string", "enum": ["low", "medium", "high", "very_high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "raw_description": {"type": "string"},
    },
    "required": [
        "terrain_type",
        "structures",
        "landmarks",
        "density",
        "confidence",
        "raw_description",
    ],
    "additionalProperties": False,
}


def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


async def describe_tile(image_bytes: bytes) -> dict | None:
    b64 = encode_image(image_bytes)
    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a satellite imagery analyst. Examine the aerial image of a tile in Lower Manhattan "
                    "and produce a structured observation. Be thorough and specific about structures, landmarks, "
                    "and terrain type. Use high confidence only when you are certain."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this satellite image tile from Lower Manhattan. "
                            "Identify the terrain type, structures visible, notable landmarks, "
                            "building/development density, and your confidence level. "
                            "Provide a concise raw description of what you see."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "tile_observation",
                "strict": True,
                "schema": OBSERVATION_SCHEMA,
            },
        },
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(CEREBRAS_API, headers=headers, json=payload)
        if resp.status_code != 200:
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)