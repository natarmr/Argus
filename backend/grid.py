from typing import Tuple, List

NORTH = 40.7130
SOUTH = 40.7000
WEST = -74.0200
EAST = -74.0050
GRID_SIZE = 10

LAT_PER_TILE = (NORTH - SOUTH) / GRID_SIZE
LNG_PER_TILE = (EAST - WEST) / GRID_SIZE


def latlng_to_tile(lat: float, lng: float) -> Tuple[int, int]:
    row = int((NORTH - lat) / LAT_PER_TILE)
    col = int((lng - WEST) / LNG_PER_TILE)
    row = max(0, min(GRID_SIZE - 1, row))
    col = max(0, min(GRID_SIZE - 1, col))
    return row, col


def tile_to_latlng(row: int, col: int) -> Tuple[float, float]:
    lat = NORTH - (row + 0.5) * LAT_PER_TILE
    lng = WEST + (col + 0.5) * LNG_PER_TILE
    return lat, lng


def tile_id(row: int, col: int) -> str:
    return f"{row}_{col}"


def get_neighbors(row: int, col: int) -> List[Tuple[int, int]]:
    neighbors = []
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        r, c = row + dr, col + dc
        if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
            neighbors.append((r, c))
    return neighbors


def bbox() -> Tuple[float, float, float, float]:
    return NORTH, SOUTH, WEST, EAST


def all_tiles() -> List[Tuple[int, int]]:
    return [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)]


def parse_tile_id(tile_id: str) -> Tuple[int, int]:
    row_str, col_str = tile_id.split("_")
    return int(row_str), int(col_str)