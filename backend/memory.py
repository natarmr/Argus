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
        "coverage_pct": round((mapped + in_progress) / total * 100, 1),
        "total_observations": total_observations,
    }


from backend.grid import GRID_SIZE