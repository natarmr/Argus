import time
import random
from backend.grid import tile_id, all_tiles, get_neighbors, parse_tile_id, GRID_SIZE
from backend.memory import collective_memory, add_observation, get_tile
from backend.memory import claim_tile, release_claim, is_claimed_by_other, claims
from backend.cesium_tiles import get_tile_image_bytes
from backend.cerebras_client import describe_tile


class DroneAgent:
    def __init__(self, drone_id: int, start: tuple[int, int] | None = None):
        self.drone_id = drone_id
        if start is None:
            start = random.choice(all_tiles())
        self.row = start[0]
        self.col = start[1]
        self.path = [(self.row, self.col)]
        self.last_observed_tile: str | None = None
        self.target_tile: str | None = None
        self._coordinator_override: bool = False

    def current_tile(self) -> str:
        return tile_id(self.row, self.col)

    async def tick(self):
        await self.observe()
        r, c = self.choose_next_move()
        self.move(r, c)

    async def observe(self) -> bool:
        tid = self.current_tile()
        if tid == self.last_observed_tile:
            return False

        print(f"[Drone {self.drone_id}] Observing tile {tid} at ({self.row},{self.col}) ...")
        img = await get_tile_image_bytes(self.row, self.col)
        if img is None:
            print(f"[Drone {self.drone_id}] Failed to fetch tile image")
            return False

        print(f"[Drone {self.drone_id}] Calling Cerebras vision ...")
        result = await describe_tile(img)
        if result is None:
            print(f"[Drone {self.drone_id}] Cerebras returned no result")
            return False

        obs = {
            "drone_id": self.drone_id,
            "timestamp": time.time(),
            "terrain_type": result["terrain_type"],
            "structures": result["structures"],
            "landmarks": result["landmarks"],
            "density": result["density"],
            "traffic_density": result["traffic_density"],
            "vehicle_count": result["vehicle_count"],
            "congestion_points": result["congestion_points"],
            "confidence": result["confidence"],
            "raw_description": result["raw_description"],
        }
        add_observation(tid, obs)
        release_claim(tid)
        self.last_observed_tile = tid
        print(f"[Drone {self.drone_id}] Tile {tid}: {result['terrain_type']} (conf={result['confidence']})")
        return True

    def choose_next_move(self) -> tuple[int, int]:
        if self.target_tile is not None:
            release_claim(self.target_tile)

        tid = self.current_tile()
        tile = get_tile(tid)

        if self._coordinator_override:
            if tid == self.target_tile:
                self._coordinator_override = False
            else:
                tr, tc = parse_tile_id(self.target_tile)
                claim_tile(self.target_tile, self.drone_id)
                return self._path_to(self.row, self.col, tr, tc)

        if tile["status"] == "unexplored":
            tile["status"] = "in_progress"
            self.target_tile = tid
            claim_tile(tid, self.drone_id)
            return self.row, self.col

        visited = {tid}
        queue = [(self.row, self.col, 0)]
        while queue:
            r, c, dist = queue.pop(0)
            for nr, nc in get_neighbors(r, c):
                ntid = tile_id(nr, nc)
                if ntid in visited:
                    continue
                visited.add(ntid)
                ntile = get_tile(ntid)
                if ntile["status"] == "unexplored" and not is_claimed_by_other(ntid, self.drone_id):
                    self.target_tile = ntid
                    claim_tile(ntid, self.drone_id)
                    return self._path_to(self.row, self.col, nr, nc)
                queue.append((nr, nc, dist + 1))

        self.target_tile = None
        return self.row, self.col

    def _path_to(self, from_row: int, from_col: int, to_row: int, to_col: int) -> tuple[int, int]:
        visited = {tile_id(from_row, from_col)}
        queue = [(from_row, from_col, None, None)]
        while queue:
            r, c, pr, pc = queue.pop(0)
            if r == to_row and c == to_col:
                if pr is not None:
                    return pr, pc
                return to_row, to_col
            for nr, nc in get_neighbors(r, c):
                ntid = tile_id(nr, nc)
                if ntid in visited:
                    continue
                visited.add(ntid)
                if pr is None:
                    queue.append((nr, nc, nr, nc))
                else:
                    queue.append((nr, nc, pr, pc))
        return to_row, to_col

    def override_target(self, tile_id_str: str, reason: str):
        if self.target_tile is not None:
            release_claim(self.target_tile)
        self.target_tile = tile_id_str
        self._coordinator_override = True
        claim_tile(tile_id_str, self.drone_id)
        print(f"[Drone {self.drone_id}] Coordinator override → {tile_id_str}: {reason}")

    def move(self, r: int, c: int):
        if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE):
            print(f"[Drone {self.drone_id}] *** OUT OF BOUNDS *** move to ({r},{c}) — STAYING at ({self.row},{self.col})")
            return
        print(f"[Drone {self.drone_id}] Moving from ({self.row},{self.col}) to ({r},{c})")
        self.row = r
        self.col = c
        self.path.append((r, c))