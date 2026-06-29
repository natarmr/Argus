# Hivemind Drone Swarm Mapper

A simulated drone swarm that collectively maps Lower Manhattan using Gemma 4 31B vision via Cerebras. Each drone is an autonomous agent; all share a collective memory that aggregates into a unified semantic map displayed on a CesiumJS 3D globe.

## File Reference

### `backend/main.py`
FastAPI application entry point. Runs the async tick loop (all drones observe and move in parallel via `asyncio.gather`), coordinates the synthesis background task, and serves three REST endpoints: `/state` (live map, drone positions, coverage stats, traffic data), `/config` (Cesium token, drone starts), and `/export` (full simulation JSON download). Also mounts the frontend static files and applies cache-busting middleware.

### `backend/drone.py`
`DroneAgent` class representing one explorer. On each tick it observes its current tile via Cerebras vision, pushes the structured observation (terrain, structures, landmarks, traffic) to collective memory, then picks the nearest unexplored tile using BFS frontier exploration. Claims tiles atomically to avoid duplicate observations. Tracks its movement path for export.

### `backend/coordinator.py`
`CoordinatorAgent` — the hivemind brain. Runs every 5 ticks: builds an ASCII coverage grid, calls Cerebras for reassignment reasoning, and issues override targets to idle or inefficiently placed drones. Also runs a local fallback heuristic that detects drones with no target and reassigns them to the globally nearest unexplored tile.

### `backend/memory.py`
Shared in-memory state store (Python dict). Defines the `Observation` and `TileMemory` schemas, the `COLOR_MAP` for terrain categories, and all access functions (`get_tile`, `add_observation`, `set_final_label`, `claim_tile`, `get_coverage_stats`). Includes optional Redis backend — falls back to in-memory dict if Redis is unavailable.

### `backend/redis_memory.py`
Redis-backed memory wrapper with the same interface as `memory.py`. `RedisMemory` class stores tiles as JSON strings and claims as separate Redis keys. `InMemoryBackend` wraps the plain dict for zero-config dev mode. Automatically used by `memory.py` if a Redis connection succeeds.

### `backend/cerebras_client.py`
Gemma 4 31B vision client for Cerebras API. Encodes tile images as base64, sends them with a structured JSON schema prompt that requests terrain type, structures, landmarks, density, traffic analysis (density, vehicle count, congestion points), and confidence. Implements exponential backoff retry on 429 rate limits.

### `backend/grid.py`
Tile grid geometry for Lower Manhattan (20×20 = 400 tiles, ~60×70m each). Provides `latlon_to_tile` / `tile_to_latlon` coordinate conversion, `get_neighbors` for BFS traversal, `all_tiles` iterator, and the canonical `GRID_SIZE` constant shared across all modules.

### `backend/cesium_tiles.py`
Fetches Bing Maps Aerial satellite imagery via Cesium ion's REST API. Converts tile grid coordinates to quadkeys, constructs XYZ tile URLs using the Bing session key, and downloads JPEG image bytes for Cerebras vision analysis. Caches the Bing key globally at startup.

### `backend/synthesis.py`
`process_pending` background task that merges all drone observations into a unified semantic map. For each tile with observations, runs majority-vote label resolution (no Cerebras call for unanimous tiles) and calls Cerebras text-only for conflicting labels. Assigns terrain colors and sets `status = "mapped"`.

### `backend/config.py`
Pydantic `Settings` class loaded from `.env` at import time. Fields: `cerebras_api_key`, `cesium_ion_token`, `tick_interval`, `grid_size`, `num_drones`, and optional `redis_host`/`port`/`db` for the Redis fallback backend.

### `frontend/index.html`
CesiumJS 3D viewer page. Loads OSM Buildings tileset, renders the 20×20 tile grid with fog-of-war (unexplored opaque, in-progress gold, mapped translucent semantic color), displays a HUD with coverage stats and terrain breakdown, shows a traffic density legend, and presents a completion banner with Download JSON / Download Map PNG buttons.

### `frontend/app.js`
Client-side logic for the CesiumJS viewer. Polls `/state` every second to update drone positions (smooth lerp animation), tile colors, traffic heatmap overlay, coverage stats, and terrain breakdown. Handles tile click popups showing observations, structures, landmarks, traffic data, and congestion points. Triggers auto-download on simulation completion.

### `requirements.txt`
Python dependencies: FastAPI + uvicorn (web server), httpx (Cerebras API client), pydantic-settings (config), python-dotenv (.env loader), and redis (optional backend).

### `AGENTS.md`
Project specification document. Defines the target area (Lower Manhattan), agent roster (Drone, Coordinator, Synthesis), collective memory schema, tick loop architecture, Cerebras usage patterns, tech stack, and build order. Kept as pure specification, not a developer guide.
