import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.memory import collective_memory, get_coverage_stats
from backend.drone import DroneAgent
from backend.cesium_tiles import get_bing_key

drone = DroneAgent(drone_id=1)


async def tick_loop():
    while True:
        await drone.observe()
        r, c = drone.choose_next_move()
        drone.move(r, c)
        await asyncio.sleep(settings.tick_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_bing_key()
    task = asyncio.create_task(tick_loop())
    yield
    task.cancel()


app = FastAPI(title="Hivemind Drone Swarm Mapper", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/state")
async def get_state():
    tiles = {}
    for tid, t in collective_memory.items():
        tiles[tid] = {
            "status": t["status"],
            "final_label": t["final_label"],
            "color": t["color"],
            "observation_count": len(t["observations"]),
        }

    return {
        "drone": {"id": drone.drone_id, "row": drone.row, "col": drone.col},
        "tiles": tiles,
        "coverage": get_coverage_stats(),
    }