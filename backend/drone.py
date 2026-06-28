import time
from backend.grid import tile_id, all_tiles, get_neighbors
from backend.memory import collective_memory, add_observation, get_tile
from backend.cesium_tiles import get_tile_image_bytes
from backend.cerebras_client import describe_tile


class DroneAgent:
    def __init__(self, drone_id: int, start_row: int = 0, start_col: int = 0):
        self.drone_id = drone_id
        self.row = start_row
        self.col = start_col
        self.last_observed_tile: str | None = None

    def current_tile(self) -> str:
        return tile_id(self.row, self.col)

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
            "confidence": result["confidence"],
            "raw_description": result["raw_description"],
        }
        add_observation(tid, obs)
        self.last_observed_tile = tid
        print(f"[Drone {self.drone_id}] Tile {tid}: {result['terrain_type']} (conf={result['confidence']})")
        return True

    def choose_next_move(self) -> tuple[int, int]:
        tid = self.current_tile()
        tile = get_tile(tid)
        if tile["status"] == "unexplored":
            tile["status"] = "in_progress"
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
                if ntile["status"] == "unexplored":
                    return self._path_to(self.row, self.col, nr, nc)
                queue.append((nr, nc, dist + 1))
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

    def move(self, r: int, c: int):
        print(f"[Drone {self.drone_id}] Moving to ({r},{c})")
        self.row = r
        self.col = c