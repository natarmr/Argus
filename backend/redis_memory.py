import json
from typing import Any, Dict, Optional
from copy import deepcopy
from backend.grid import GRID_SIZE

DEFAULT_TILE_MEMORY = {
    "observations": [],
    "final_label": "unknown",
    "color": "#FFFFFF",
    "status": "unexplored",
}


class RedisMemory:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        import redis as _redis
        self._r = _redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self._r.ping()

    def _tile_key(self, tile_id: str) -> str:
        return f"tile:{tile_id}"

    def get_tile(self, tile_id: str) -> dict:
        key = self._tile_key(tile_id)
        raw = self._r.get(key)
        if raw is None:
            tile = deepcopy(DEFAULT_TILE_MEMORY)
            self._r.set(key, json.dumps(tile))
            return tile
        return json.loads(raw)

    def _save_tile(self, tile_id: str, data: dict):
        self._r.set(self._tile_key(tile_id), json.dumps(data))

    def add_observation(self, tile_id: str, obs: dict):
        tile = self.get_tile(tile_id)
        tile["observations"].append(obs)
        if tile["status"] == "unexplored":
            tile["status"] = "in_progress"
        self._save_tile(tile_id, tile)

    def set_final_label(self, tile_id: str, label: str, color: str):
        tile = self.get_tile(tile_id)
        tile["final_label"] = label
        tile["color"] = color
        tile["status"] = "mapped"
        self._save_tile(tile_id, tile)

    def claim_tile(self, tile_id: str, drone_id: int) -> bool:
        key = f"claim:{tile_id}"
        existing = self._r.get(key)
        if existing is not None and int(existing) != drone_id:
            return False
        self._r.set(key, str(drone_id))
        return True

    def release_claim(self, tile_id: str):
        self._r.delete(f"claim:{tile_id}")

    def is_claimed_by_other(self, tile_id: str, drone_id: int) -> bool:
        existing = self._r.get(f"claim:{tile_id}")
        return existing is not None and int(existing) != drone_id

    def get_claims(self) -> dict:
        return {k.split(":", 1)[1]: int(v) for k, v in self._r.scan_iter("claim:*")}

    def _all_tiles(self) -> list[tuple[str, dict]]:
        results = []
        for key in self._r.scan_iter("tile:*"):
            tid = key.split(":", 1)[1]
            raw = self._r.get(key)
            if raw:
                results.append((tid, json.loads(raw)))
        return results

    def get_coverage_stats(self) -> Dict[str, Any]:
        total = GRID_SIZE * GRID_SIZE
        mapped = 0
        in_progress = 0
        total_obs = 0
        for _, tile in self._all_tiles():
            if tile["status"] == "mapped":
                mapped += 1
            elif tile["status"] == "in_progress":
                in_progress += 1
            total_obs += len(tile["observations"])
        return {
            "mapped": mapped,
            "in_progress": in_progress,
            "unexplored": total - mapped - in_progress,
            "total_tiles": total,
            "coverage_pct": round(mapped / total * 100, 1) if total > 0 else 0.0,
            "total_observations": total_obs,
        }

    def items(self):
        return self._all_tiles()

    def __iter__(self):
        for key in self._r.scan_iter("tile:*"):
            yield key.split(":", 1)[1]

    def __contains__(self, tile_id: str) -> bool:
        return self._r.exists(self._tile_key(tile_id)) > 0

    def __len__(self) -> int:
        count = 0
        for _ in self._r.scan_iter("tile:*"):
            count += 1
        return count


class InMemoryBackend(dict):
    def get_tile(self, tile_id: str) -> dict:
        if tile_id not in self:
            self[tile_id] = deepcopy(DEFAULT_TILE_MEMORY)
        return self[tile_id]

    def add_observation(self, tile_id: str, obs: dict):
        tile = self.get_tile(tile_id)
        tile["observations"].append(obs)
        if tile["status"] == "unexplored":
            tile["status"] = "in_progress"

    def set_final_label(self, tile_id: str, label: str, color: str):
        tile = self.get_tile(tile_id)
        tile["final_label"] = label
        tile["color"] = color
        tile["status"] = "mapped"

    def get_coverage_stats(self) -> Dict[str, Any]:
        total = GRID_SIZE * GRID_SIZE
        mapped = sum(1 for t in self.values() if isinstance(t, dict) and t.get("status") == "mapped")
        in_progress = sum(1 for t in self.values() if isinstance(t, dict) and t.get("status") == "in_progress")
        total_obs = sum(len(t.get("observations", [])) for t in self.values() if isinstance(t, dict))
        return {
            "mapped": mapped,
            "in_progress": in_progress,
            "unexplored": total - mapped - in_progress,
            "total_tiles": total,
            "coverage_pct": round(mapped / total * 100, 1) if total > 0 else 0.0,
            "total_observations": total_obs,
        }
