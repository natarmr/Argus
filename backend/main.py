import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.memory import collective_memory, get_coverage_stats, claims
from backend.drone import DroneAgent
from backend.cesium_tiles import get_bing_key
from backend.grid import all_tiles, tile_id
from backend.coordinator import CoordinatorAgent, COORDINATOR_INTERVAL
import random

start_tiles = random.sample(all_tiles(), settings.num_drones)
drones = [DroneAgent(i, start_tiles[i]) for i in range(settings.num_drones)]
coordinator = CoordinatorAgent()


async def tick_loop():
    tick_count = 0
    while True:
        await asyncio.gather(*[d.tick() for d in drones])
        tick_count += 1
        if tick_count % COORDINATOR_INTERVAL == 0:
            reassignments = await coordinator.review(drones, collective_memory)
            for r in reassignments:
                did = r["drone_id"]
                target = tile_id(r["target_tile"][0], r["target_tile"][1])
                drones[did].override_target(target, r["reason"])
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
        "drones": [
            {"id": d.drone_id, "row": d.row, "col": d.col, "target": d.target_tile}
            for d in drones
        ],
        "tiles": tiles,
        "claims": dict(claims),
        "coverage": get_coverage_stats(),
    }