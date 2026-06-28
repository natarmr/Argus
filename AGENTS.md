# AGENTS.md — Hivemind Drone Swarm Mapper
## Project Overview
A simulated drone swarm that collectively maps an unknown area of Lower Manhattan using
multimodal AI. Each drone is an autonomous agent with its own vision and movement logic.
All agents share a collective memory (the "hivemind") that aggregates into a single unified
semantic map. Built on Gemma 4 31B via Cerebras for fast parallel inference.
---
## Target Area
**Lower Manhattan, New York City**
```
North: 40.7130
South: 40.7000
West:  -74.0200
East:  -74.0050
```
Grid: 10×10 = 100 tiles (~120m × 140m per tile)
---
## Agent Roster
### 1. Drone Agent (N instances, default: 10)
**File:** `backend/drone.py`
**Role:** Individual explorer. Flies over the grid, observes tiles via Gemma 4 vision,
reports structured observations to collective memory, and selects its next move.
**Inputs:**
- Current tile image (rendered from CesiumJS viewport snapshot at tile coordinates)
- Own position history
- Set of tiles currently claimed by other drones (to avoid overlap)
**Per-tick behavior:**
1. Fetch image of current tile
2. Call Gemma 4 vision → produce structured observation:
   ```json
   {
     "terrain_type": "commercial",
     "structures": ["skyscrapers", "parking garage"],
     "landmarks": ["One World Trade Center"],
     "density": "high",
     "confidence": 0.92
   }
   ```
3. Push observation to Collective Memory
4. Run frontier algorithm → pick nearest unexplored tile not claimed by another drone
5. Move to that tile
**Movement policy:** Frontier-based exploration (BFS to nearest uncovered tile).
Coordinator Agent can override the target with a priority assignment.
**Parallelism:** All drone agents fire their vision calls simultaneously via asyncio.
---
### 2. Coordinator Agent (1 instance)
**File:** `backend/coordinator.py`
**Role:** The hivemind brain. Runs every 5 ticks. Reviews collective map state and
drone positions, identifies inefficiencies, and reassigns drones to priority zones.
**Inputs:**
- Full Collective Memory snapshot
- All drone current positions and assigned targets
- Coverage heatmap (which tiles have been seen, how many times, confidence scores)
**Behavior:**
1. Identify coverage gaps (unexplored tiles, low-confidence tiles)
2. Identify redundancy (multiple drones converging on same zone)
3. Call Gemma 4 → produce reassignment instructions:
   ```json
   {
     "reassignments": [
       {"drone_id": 3, "target_tile": [7, 4], "reason": "gap in northeast quadrant"},
       {"drone_id": 7, "target_tile": [2, 9], "reason": "low confidence cluster"}
     ]
   }
   ```
4. Push reassignments to drone state store
**Prompt strategy:** Provide Coordinator with a compact ASCII representation of the
coverage grid + drone positions so it fits cleanly in context.
---
### 3. Synthesis Agent (1 instance)
**File:** `backend/synthesis.py`
**Role:** Produces the final unified map. Runs continuously in the background,
merging all drone observations into a single coherent semantic layer.
**Inputs:**
- Full Collective Memory (all tile observations from all drones)
**Behavior:**
1. For each tile with multiple observations, resolve conflicts (majority vote on labels,
   average confidence scores)
2. Call Gemma 4 → produce unified tile descriptor and semantic category
3. Assign color category for frontend overlay:
   - `residential` → blue
   - `commercial` → orange  
   - `industrial` → grey
   - `green_space` → green
   - `water` → cyan
   - `infrastructure` → yellow
   - `unknown` → white
4. Output structured map state that frontend polls
**Output schema:**
```json
{
  "tile_id": "3_7",
  "final_label": "commercial",
  "description": "Dense high-rise commercial district with street-level retail",
  "confidence": 0.89,
  "observed_by": [1, 4, 7],
  "color": "#FF8C00"
}
```
---
## Collective Memory
**File:** `backend/memory.py`
Shared in-memory store (Python dict, optionally Redis for production demo).
All agents read and write to this. Acts as the hivemind's shared brain.
**Schema:**
```python
collective_memory = {
    "tile_id": {                    # e.g. "3_7"
        "observations": [           # list of all drone observations for this tile
            {
                "drone_id": int,
                "timestamp": float,
                "terrain_type": str,
                "structures": list,
                "landmarks": list,
                "density": str,
                "confidence": float,
                "raw_description": str
            }
        ],
        "final_label": str,         # set by Synthesis Agent
        "color": str,               # hex color for frontend
        "status": "unexplored" | "in_progress" | "mapped"
    }
}
```
---
## Tile Image Capture

Tile images for Gemma 4 vision are fetched server-side using the **Cesium ion REST API**.
Cesium ion hosts satellite imagery assets (including Bing Maps Aerial) accessible as
standard XYZ tile URLs once you have an access token.
**File:** `backend/main.py`
```
TICK_INTERVAL = 2 seconds

every tick:
  async gather:
    for each drone:
      observe current tile → push to memory → compute next move

  every 5 ticks:
    coordinator reviews state → issues reassignments

  every tick:
    synthesis agent updates unified map state

  frontend polls /state endpoint → receives:
    - drone positions
    - revealed tiles + semantic labels
    - coverage percentage
    - observations/sec metric
```
---
## Cerebras Usage

All Gemma 4 31B calls go through Cerebras API.

| Agent | Call type | Frequency | Parallelism |
|---|---|---|---|
| Drone Agent | vision + description | every tick per drone | N simultaneous |
| Coordinator Agent | structured reasoning | every 5 ticks | 1 call |
| Synthesis Agent | label merging | continuous | 1 call per updated tile |
---
## Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, asyncio |
| LLM | Gemma 4 31B via Cerebras API |
| Tile images | CesiumJS canvas snapshot at tile coordinates |
| 3D City | Cesium OSM Buildings (350M+ buildings, free, streams via Cesium ion) |
| Frontend | CesiumJS, vanilla JS |
| State store | Python dict (in-memory) |
| Comms | FastAPI REST, frontend polls /state every 1s |

## Repo Structure
  |backend|   # FastAPI app, agents, memory, API endpoints|
  |frontend|     # CesiumJS app, static assets, index.html|
---
## Build Order 
|`grid.py` + `memory.py` + tile coordinate helpers working |
|Single drone agent working end-to-end (vision → memory → move) |
|Scale to 10 drones with asyncio, tick loop running |
|Coordinator agent + reassignment logic |
|FastAPI `/state` endpoint + CesiumJS frontend with OSM Buildings loading |
|Fog of war overlay + drone markers animating + semantic color layer |
|Synthesis agent + final unified map output |
---

## DOCS
Gemma 4: https://inference-docs.cerebras.ai/models/gemma-4-31b
Cesium ION: https://cesium.com/learn/ion/rest-api/#tag/Assets