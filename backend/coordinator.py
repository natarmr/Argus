import json
import asyncio
import httpx
from backend.config import settings
from backend.grid import GRID_SIZE, tile_id, parse_tile_id

COORDINATOR_INTERVAL = 5
REQUIRED_FIELDS = {"drone_id", "target_tile", "reason"}

COORDINATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "reassignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "minimum": 0, "maximum": 9},
                    "target_tile": {
                        "type": "array",
                        "prefixItems": [
                            {"type": "integer", "minimum": 0, "maximum": 9},
                            {"type": "integer", "minimum": 0, "maximum": 9},
                        ],
                        "items": False,
                    },
                    "reason": {"type": "string"},
                },
                "required": ["drone_id", "target_tile", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reassignments"],
    "additionalProperties": False,
}


def _build_ascii_grid(memory: dict, drones: list) -> str:
    grid = {}
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            grid[(r, c)] = "U"

    drone_positions = {}
    for d in drones:
        drone_positions[(d.row, d.col)] = d.drone_id

    for tid, t in memory.items():
        r, c = parse_tile_id(tid)
        if t["status"] == "in_progress":
            grid[(r, c)] = "."
        elif t["status"] == "mapped":
            grid[(r, c)] = "M"

    for (r, c), did in drone_positions.items():
        tid = tile_id(r, c)
        tile = memory.get(tid, {})
        if tile.get("status") == "unexplored":
            grid[(r, c)] = str(did)

    lines = ["   " + " ".join(str(c) for c in range(GRID_SIZE))]
    for r in range(GRID_SIZE):
        row = f"{r:2} " + " ".join(grid[(r, c)] for c in range(GRID_SIZE))
        lines.append(row)

    return "\n".join(lines)


def _build_summary(memory: dict, drones: list) -> str:
    observed = sum(1 for t in memory.values() if t["status"] in ("in_progress", "mapped"))
    confs = []
    for t in memory.values():
        for o in t["observations"]:
            confs.append(o.get("confidence", 0))
    avg_conf = sum(confs) / len(confs) if confs else 0
    return f"Coverage: {observed}/{GRID_SIZE*GRID_SIZE}  Drones: {len(drones)}  Avg confidence: {avg_conf:.2f}"


class CoordinatorAgent:
    def __init__(self):
        self.last_reassignments: list[dict] = []

    async def review(self, drones: list, memory: dict) -> list[dict]:
        grid_str = _build_ascii_grid(memory, drones)
        summary = _build_summary(memory, drones)

        prompt = (
            "You are a drone swarm coordinator exploring Lower Manhattan. "
            "The grid below shows the current state of a 10x10 tile map.\n\n"
            "Legend:\n"
            "  U = unexplored\n"
            "  . = drone currently observing this tile\n"
            "  M = mapped (fully analyzed)\n"
            "  0-9 = drone ID occupying this tile\n\n"
            f"{grid_str}\n\n"
            f"{summary}\n\n"
            "Identify inefficiencies and produce reassignments. "
            "Common issues:\n"
            "  - Multiple drones converging on the same quadrant\n"
            "  - Large gaps of unexplored tiles with no drone nearby\n"
            "  - Drones in already-mapped areas\n\n"
            "Output a list of reassignments. Each must have: drone_id (0-9), "
            "target_tile as [row, col], and a reason string. "
            "If no reassignments are needed, return an empty list."
        )

        payload = {
            "model": "gemma-4-31b",
            "messages": [
                {"role": "system", "content": "You are a drone swarm coordinator. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "reassignments",
                    "strict": True,
                    "schema": COORDINATOR_SCHEMA,
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
                        print(f"[Coordinator] Error {resp.status_code}")
                        return []
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    reassignments = parsed.get("reassignments", [])
                    print(f"[Coordinator] {len(reassignments)} reassignment(s) issued")
                    for r in reassignments:
                        print(f"  Drone {r['drone_id']} -> [{r['target_tile'][0]},{r['target_tile'][1]}] : {r['reason']}")
                    self.last_reassignments = reassignments
                    return reassignments
            except Exception as e:
                print(f"[Coordinator] Exception: {e}")
                continue

        return []