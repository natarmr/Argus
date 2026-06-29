import asyncio
import random
import datetime
import json
import tempfile
import traceback
from contextlib import asynccontextmanager
from collections import Counter

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.memory import collective_memory, get_coverage_stats, claims
from backend.drone import DroneAgent
from backend.cesium_tiles import get_bing_key
from backend.grid import all_tiles, tile_id
from backend.coordinator import CoordinatorAgent, COORDINATOR_INTERVAL
from backend.synthesis import process_pending

IDLE_THRESHOLD = 3

start_tiles = random.sample(all_tiles(), settings.num_drones)
drones = [DroneAgent(i, start_tiles[i]) for i in range(settings.num_drones)]
coordinator = CoordinatorAgent()
simulation_complete = False
idle_ticks = 0


async def tick_loop():
    global simulation_complete, idle_ticks
    tick_count = 0
    while True:
        try:
            await asyncio.gather(*[d.tick() for d in drones])
        except Exception as e:
            print(f"[TickLoop] ERROR in drone tick: {e}")
            traceback.print_exc()
            await asyncio.sleep(settings.tick_interval)
            continue
        tick_count += 1

        stats = get_coverage_stats()
        if stats["mapped"] >= stats["total_tiles"]:
            idle_ticks += 1
            if idle_ticks >= IDLE_THRESHOLD:
                simulation_complete = True
                print("[TickLoop] All tiles mapped — simulation complete")
                break
        else:
            idle_ticks = 0

        if tick_count % COORDINATOR_INTERVAL == 0:
            try:
                reassignments = await coordinator.review(drones, collective_memory)
                for r in reassignments:
                    did = r["drone_id"]
                    target = tile_id(r["target_tile"][0], r["target_tile"][1])
                    drones[did].override_target(target, r["reason"])
            except Exception as e:
                print(f"[TickLoop] ERROR in coordinator review: {e}")
                traceback.print_exc()
        await asyncio.sleep(settings.tick_interval)


async def synthesis_loop():
    while not simulation_complete:
        try:
            count = await process_pending(collective_memory)
            if count:
                print(f"[SynthesisLoop] Mapped {count} tile(s) this cycle")
        except Exception as e:
            print(f"[SynthesisLoop] ERROR: {e}")
            traceback.print_exc()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global simulation_complete
    await get_bing_key()
    tick_task = asyncio.create_task(tick_loop())
    synth_task = asyncio.create_task(synthesis_loop())
    yield
    if not simulation_complete:
        tick_task.cancel()
    synth_task.cancel()


app = FastAPI(title="Hivemind Drone Swarm Mapper", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/index.html", "/app.js"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/state")
async def get_state():
    tiles = {}
    for tid, t in collective_memory.items():
        obs = t.get("observations", [])
        best = max(obs, key=lambda o: o.get("confidence", 0)) if obs else None
        drones_set = sorted(set(o["drone_id"] for o in obs)) if obs else []
        structures = list(dict.fromkeys(s for o in obs for s in o.get("structures", [])))
        landmarks = list(dict.fromkeys(l for o in obs for l in o.get("landmarks", [])))
        congestion_points = list(dict.fromkeys(cp for o in obs for cp in o.get("congestion_points", [])))
        total_vehicles = sum(o.get("vehicle_count", 0) for o in obs)
        obs_count = len(obs) or 1
        avg_vehicles = round(total_vehicles / obs_count)
        # traffic_density from the most-vehicles observation (worst-case)
        traffic_density = "none"
        if obs:
            traffic_density = max(obs, key=lambda o: {"none": 0, "light": 1, "moderate": 2, "heavy": 3, "gridlock": 4}.get(o.get("traffic_density", "none"), 0)).get("traffic_density", "none")
        tiles[tid] = {
            "status": t["status"],
            "final_label": t["final_label"],
            "color": t["color"],
            "observation_count": len(obs),
            "top_confidence": best["confidence"] if best else None,
            "description": best["raw_description"] if best else None,
            "structures": structures,
            "landmarks": landmarks,
            "traffic_density": traffic_density,
            "vehicle_count": avg_vehicles,
            "congestion_points": congestion_points,
            "observed_by": drones_set,
        }

    return {
        "drones": [
            {"id": d.drone_id, "row": d.row, "col": d.col, "target": d.target_tile}
            for d in drones
        ],
        "tiles": tiles,
        "claims": dict(claims),
        "coverage": get_coverage_stats(),
        "simulation_complete": simulation_complete,
    }


@app.get("/config")
async def get_config():
    return {
        "cesiumToken": settings.cesium_ion_token,
        "numDrones": settings.num_drones,
        "tickInterval": settings.tick_interval,
        "north": 40.7130,
        "south": 40.7000,
        "west": -74.0200,
        "east": -74.0050,
        "drone_starts": [{"id": d.drone_id, "row": d.row, "col": d.col} for d in drones],
    }


@app.get("/export")
async def export_map():
    stats = get_coverage_stats()

    tiles_export = {}
    label_counts = Counter()
    for tid, t in collective_memory.items():
        tile_data = {
            "status": t["status"],
            "final_label": t["final_label"],
            "color": t["color"],
            "observation_count": len(t["observations"]),
            "observations": t["observations"],
        }
        tiles_export[tid] = tile_data
        if t["status"] == "mapped":
            label_counts[t["final_label"]] += 1

    total_mapped = sum(label_counts.values()) or 1
    breakdown = {
        label: {"count": count, "pct": round(count / total_mapped * 100, 1)}
        for label, count in label_counts.most_common()
    }

    payload = {
        "simulation": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "grid_size": 20,
            "num_drones": settings.num_drones,
            "total_tiles": stats["total_tiles"],
            "mapped": stats["mapped"],
            "in_progress": stats["in_progress"],
            "total_observations": stats["total_observations"],
            "simulation_complete": simulation_complete,
        },
        "breakdown": breakdown,
        "tiles": tiles_export,
        "drones": [
            {"id": d.drone_id, "path": d.path}
            for d in drones
        ],
    }

    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(payload, f, indent=2)
    f.close()
    return FileResponse(f.name, media_type="application/json",
                        filename=f"hivemind-map-{datetime.date.today().isoformat()}.json",
                        headers={"Content-Disposition": "attachment"})


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")