from typing import TypedDict, List, Dict, Any
from datetime import datetime
from copy import deepcopy


class Observation(TypedDict):
    drone_id: int
    timestamp: float
    terrain_type: str
    structures: List[str]
    landmarks: List[str]
    density: str
    confidence: float
    raw_description: str


class TileMemory(TypedDict):
    observations: List[Observation]
    final_label: str
    color: str
    status: str


collective_memory: Dict[str, TileMemory] = {}
claims: Dict[str, int] = {}


def claim_tile(tile_id: str, drone_id: int) -> bool:
    existing = claims.get(tile_id)
    if existing is not None and existing != drone_id:
        return False
    claims[tile_id] = drone_id
    return True


def release_claim(tile_id: str):
    claims.pop(tile_id, None)


def is_claimed_by_other(tile_id: str, drone_id: int) -> bool:
    claimant = claims.get(tile_id)
    return claimant is not None and claimant != drone_id


DEFAULT_TILE_MEMORY: TileMemory = {
    "observations": [],
    "final_label": "unknown",
    "color": "#FFFFFF",
    "status": "unexplored",
}


def get_tile(tile_id: str) -> TileMemory:
    if tile_id not in collective_memory:
        collective_memory[tile_id] = deepcopy(DEFAULT_TILE_MEMORY)
    return collective_memory[tile_id]


def add_observation(tile_id: str, obs: Observation) -> None:
    tile = get_tile(tile_id)
    tile["observations"].append(obs)
    if tile["status"] == "unexplored":
        tile["status"] = "in_progress"


def set_final_label(tile_id: str, label: str, color: str) -> None:
    tile = get_tile(tile_id)
    tile["final_label"] = label
    tile["color"] = color
    tile["status"] = "mapped"


def get_coverage_stats() -> Dict[str, Any]:
    total = GRID_SIZE * GRID_SIZE
    mapped = sum(1 for t in collective_memory.values() if t["status"] == "mapped")
    in_progress = sum(1 for t in collective_memory.values() if t["status"] == "in_progress")
    unexplored = total - mapped - in_progress
    total_observations = sum(len(t["observations"]) for t in collective_memory.values())
    return {
        "mapped": mapped,
        "in_progress": in_progress,
        "unexplored": unexplored,
        "total_tiles": total,
        "coverage_pct": round(mapped / total * 100, 1) if total > 0 else 0.0,
        "total_observations": total_observations,
    }


from backend.grid import GRID_SIZE


COLOR_MAP: dict[str, str] = {
    "residential": "#E91E63",
    "commercial": "#FF8C00",
    "industrial": "#9E9E9E",
    "green_space": "#4CAF50",
    "water": "#2196F3",
    "infrastructure": "#FFEB3B",
    "unknown": "#FFFFFF",
}


def get_terrain_color(label: str) -> str:
    return COLOR_MAP.get(label, COLOR_MAP["unknown"])


# ---------------------------------------------------------------------------
# Optional Redis backend — fall back to in-memory if unavailable
# ---------------------------------------------------------------------------
try:
    from backend.config import settings
    r_host = settings.redis_host
    r_port = settings.redis_port
    r_db = settings.redis_db
except Exception:
    r_host, r_port, r_db = "localhost", 6379, 0

try:
    import redis as _redis_module
    _r_conn = _redis_module.Redis(host=r_host, port=r_port, db=r_db, decode_responses=True,
                                  socket_connect_timeout=2)
    _r_conn.ping()
    _redis_ok = True
except Exception:
    _redis_ok = False

if _redis_ok:
    import json
    from copy import deepcopy

    def _tkey(tid: str) -> str:
        return f"tile:{tid}"

    def _ckey(tid: str) -> str:
        return f"claim:{tid}"

    def get_tile(tile_id: str) -> TileMemory:
        raw = _r_conn.get(_tkey(tile_id))
        if raw is None:
            tile = deepcopy(DEFAULT_TILE_MEMORY)
            _r_conn.set(_tkey(tile_id), json.dumps(tile))
            return tile
        return json.loads(raw)

    def _save_tile(tile_id: str, data: dict):
        _r_conn.set(_tkey(tile_id), json.dumps(data))

    def add_observation(tile_id: str, obs: Observation):
        tile = get_tile(tile_id)
        tile["observations"].append(obs)
        if tile["status"] == "unexplored":
            tile["status"] = "in_progress"
        _save_tile(tile_id, tile)

    def set_final_label(tile_id: str, label: str, color: str):
        tile = get_tile(tile_id)
        tile["final_label"] = label
        tile["color"] = color
        tile["status"] = "mapped"
        _save_tile(tile_id, tile)

    def claim_tile(tile_id: str, drone_id: int) -> bool:
        existing = _r_conn.get(_ckey(tile_id))
        if existing is not None and int(existing) != drone_id:
            return False
        _r_conn.set(_ckey(tile_id), str(drone_id))
        return True

    def release_claim(tile_id: str):
        _r_conn.delete(_ckey(tile_id))

    def is_claimed_by_other(tile_id: str, drone_id: int) -> bool:
        existing = _r_conn.get(_ckey(tile_id))
        return existing is not None and int(existing) != drone_id

    def get_coverage_stats() -> dict:
        total = GRID_SIZE * GRID_SIZE
        mapped = 0
        in_progress = 0
        total_obs = 0
        for key in _r_conn.scan_iter("tile:*"):
            raw = _r_conn.get(key)
            if raw:
                t = json.loads(raw)
                if t["status"] == "mapped":
                    mapped += 1
                elif t["status"] == "in_progress":
                    in_progress += 1
                total_obs += len(t.get("observations", []))
        return {
            "mapped": mapped,
            "in_progress": in_progress,
            "unexplored": total - mapped - in_progress,
            "total_tiles": total,
            "coverage_pct": round(mapped / total * 100, 1) if total > 0 else 0.0,
            "total_observations": total_obs,
        }

    # Build a dict view over Redis tiles so iteration still works
    class _RedisTileView(dict):
        def __getitem__(self, tile_id):
            return get_tile(tile_id)
        def __setitem__(self, tile_id, data):
            _save_tile(tile_id, data)
        def __contains__(self, tile_id):
            return _r_conn.exists(_tkey(tile_id)) > 0
        def __iter__(self):
            for key in _r_conn.scan_iter("tile:*"):
                yield key.split(":", 1)[1]
        def __len__(self):
            n = 0
            for _ in _r_conn.scan_iter("tile:*"):
                n += 1
            return n
        def items(self):
            for tid in self:
                yield tid, get_tile(tid)
        def values(self):
            for tid in self:
                yield get_tile(tid)

    collective_memory: dict = _RedisTileView()
    claims: dict = {}  # claims handled via Redis keys; keep empty dict for backward compat

    print("[memory] Redis backend active")

else:
    print("[memory] Redis unavailable; using in-memory dict")