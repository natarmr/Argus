import math
import httpx
from backend.config import settings
from backend.grid import tile_to_latlng

CESIUM_API = "https://api.cesium.com/v1"
BING_ASSET_ID = 2


def _latlng_to_global_xy(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    n = 2.0 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int(
        (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi)
        / 2.0
        * n
    )
    return x, y


def _global_xy_to_quadkey(x: int, y: int, zoom: int) -> str:
    qk = []
    for z in range(zoom, 0, -1):
        mask = 1 << (z - 1)
        digit = 0
        if (x & mask) != 0:
            digit = 1
        if (y & mask) != 0:
            digit += 2
        qk.append(str(digit))
    return "".join(qk)


async def get_bing_key() -> str | None:
    headers = {"Authorization": f"Bearer {settings.cesium_ion_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{CESIUM_API}/assets/{BING_ASSET_ID}/endpoint",
            headers=headers,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("options", {}).get("key")


def bing_tile_url(lat: float, lng: float, zoom: int, bing_key: str) -> str:
    x, y = _latlng_to_global_xy(lat, lng, zoom)
    quadkey = _global_xy_to_quadkey(x, y, zoom)
    subdomain = chr(ord("0") + (x + y) % 4)
    return (
        f"https://ecn.t{subdomain}.tiles.virtualearth.net/tiles/a{quadkey}.jpeg"
        f"?g=15291&key={bing_key}"
    )


async def get_tile_image_bytes(row: int, col: int, zoom: int = 18) -> bytes | None:
    bing_key = await get_bing_key()
    if bing_key is None:
        return None
    lat, lng = tile_to_latlng(row, col)
    url = bing_tile_url(lat, lng, zoom, bing_key)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        return resp.content