import json
import asyncio
import httpx
from collections import Counter
from backend.config import settings
from backend.memory import set_final_label, get_terrain_color, TileMemory

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "terrain_type": {
            "type": "string",
            "enum": ["residential", "commercial", "industrial", "green_space", "water", "infrastructure", "unknown"],
        },
        "merged_structures": {"type": "array", "items": {"type": "string"}},
        "merged_landmarks": {"type": "array", "items": {"type": "string"}},
        "density": {"type": "string", "enum": ["low", "medium", "high", "very_high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "unified_description": {"type": "string"},
    },
    "required": ["terrain_type", "merged_structures", "merged_landmarks", "density", "confidence", "unified_description"],
    "additionalProperties": False,
}

_last_obs_count: dict[str, int] = {}


def _resolve_locally(observations: list) -> dict | None:
    if not observations:
        return None

    types = [o["terrain_type"] for o in observations]
    majority_type = Counter(types).most_common(1)[0][0]
    avg_conf = sum(o["confidence"] for o in observations) / len(observations)
    best = max(observations, key=lambda o: o["confidence"])

    structures = list(dict.fromkeys(s for o in observations for s in o.get("structures", [])))
    landmarks = list(dict.fromkeys(l for o in observations for l in o.get("landmarks", [])))
    densities = [o["density"] for o in observations]
    density = Counter(densities).most_common(1)[0][0]

    return {
        "terrain_type": majority_type,
        "merged_structures": structures,
        "merged_landmarks": landmarks,
        "density": density,
        "confidence": round(avg_conf, 3),
        "unified_description": best["raw_description"],
    }


async def _call_cerebras(observations: list) -> dict | None:
    obs_text = "\n".join(
        f"Observation {i+1} (drone {o['drone_id']}, confidence {o['confidence']}): "
        f"terrain={o['terrain_type']}, density={o['density']}, "
        f"structures={o.get('structures', [])}, landmarks={o.get('landmarks', [])}, "
        f"description=\"{o['raw_description']}\""
        for i, o in enumerate(observations)
    )

    payload = {
        "model": "gemma-4-31b",
        "messages": [
            {
                "role": "system",
                "content": "You are a geographic synthesis agent. Merge multiple observations of the same "
                           "Lower Manhattan tile into a single unified description. Resolve conflicts by "
                           "considering confidence scores and consistency. Be concise.",
            },
            {
                "role": "user",
                "content": f"Merge these observations into one unified tile descriptor:\n\n{obs_text}",
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "synthesis",
                "strict": True,
                "schema": SYNTHESIS_SCHEMA,
            },
        },
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.cerebras.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code != 200:
                    print(f"[Synthesis] Error {resp.status_code}: {resp.text[:200]}")
                    return None
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                print(f"[Synthesis] Cerebras: {parsed['terrain_type']} (conf={parsed['confidence']}, {data['usage']['total_tokens']} tokens)")
                return parsed
        except Exception as e:
            print(f"[Synthesis] Exception: {e}")
            continue

    return None


async def process_pending(memory: dict) -> int:
    global _last_obs_count
    mapped = 0

    for tile_id, tile in list(memory.items()):
        if tile["status"] != "in_progress":
            continue
        obs = tile.get("observations", [])
        if not obs:
            continue

        prev = _last_obs_count.get(tile_id, 0)
        if len(obs) == prev:
            continue
        _last_obs_count[tile_id] = len(obs)

        types = {o["terrain_type"] for o in obs}
        if len(types) == 1:
            result = _resolve_locally(obs)
        else:
            print(f"[Synthesis] Tile {tile_id} has {len(types)} conflicting types — calling Cerebras")
            result = await _call_cerebras(obs)

        if result is None:
            continue

        label = result["terrain_type"]
        color = get_terrain_color(label)
        set_final_label(tile_id, label, color)
        mapped += 1
        print(f"[Synthesis] Tile {tile_id} -> {label} ({color})")

    return mapped
