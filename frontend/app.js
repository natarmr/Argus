const NORTH = 40.7130;
const SOUTH = 40.7000;
const WEST = -74.0200;
const EAST = -74.0050;
const GRID_SIZE = 20;
const LAT_PER_TILE = (NORTH - SOUTH) / GRID_SIZE;
const LNG_PER_TILE = (EAST - WEST) / GRID_SIZE;
const ANIM_LERP = 0.12;

const LABEL_DISPLAY = {
    residential: "residential",
    commercial: "commercial",
    industrial: "industrial",
    green_space: "green space",
    water: "water",
    infrastructure: "infrastructure",
    unknown: "unknown",
};

const TILE_COLOR_MAP = {
    residential: "#E91E63",
    commercial: "#FF8C00",
    industrial: "#9E9E9E",
    green_space: "#4CAF50",
    water: "#2196F3",
    infrastructure: "#FFEB3B",
    unknown: "#FFFFFF",
};

async function init() {
    const configResp = await fetch("/config");
    const config = await configResp.json();
    Cesium.Ion.defaultAccessToken = config.cesiumToken;

    const viewer = new Cesium.Viewer("cesiumContainer", {
        animation: false,
        timeline: false,
        baseLayerPicker: false,
        fullscreenButton: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        geocoder: false,
        infoBox: false,
        selectionIndicator: false,
        terrain: Cesium.Terrain.fromWorldTerrain(),
    });

    const tileset = await Cesium.createOsmBuildingsAsync();
    viewer.scene.primitives.add(tileset);

    const rect = Cesium.Rectangle.fromDegrees(WEST, SOUTH, EAST, NORTH);
    viewer.camera.flyTo({
        destination: rect,
        orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
        duration: 0,
    });

    const numDrones = config.numDrones;
    const droneStarts = config.drone_starts || [];

    const droneMarkers = [];
    const droneAnim = [];
    for (let i = 0; i < numDrones; i++) {
        const start = droneStarts[i] || { row: 10, col: 10 };
        const lat = NORTH - (start.row + 0.5) * LAT_PER_TILE;
        const lng = WEST + (start.col + 0.5) * LNG_PER_TILE;
        const pos = Cesium.Cartesian3.fromDegrees(lng, lat, 80);
        const marker = viewer.entities.add({
            position: pos,
            point: {
                pixelSize: 10, color: Cesium.Color.YELLOW,
                outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5,
            },
            label: {
                text: String(i),
                font: "bold 11px monospace",
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -4),
                showBackground: true,
                backgroundColor: new Cesium.Color(0, 0, 0, 0.5),
            },
        });
        droneMarkers.push(marker);
        droneAnim.push({ current: pos.clone(), target: pos.clone() });
    }

    viewer.clock.onTick.addEventListener(() => {
        for (let i = 0; i < numDrones; i++) {
            const a = droneAnim[i];
            Cesium.Cartesian3.lerp(a.current, a.target, ANIM_LERP, a.current);
            droneMarkers[i].position = a.current;
        }
    });

    const tileEntities = {};
    for (let r = 0; r < GRID_SIZE; r++) {
        for (let c = 0; c < GRID_SIZE; c++) {
            const n = NORTH - r * LAT_PER_TILE;
            const s = n - LAT_PER_TILE;
            const e = WEST + (c + 1) * LNG_PER_TILE;
            const w = WEST + c * LNG_PER_TILE;
            const ent = viewer.entities.add({
                name: r + "_" + c,
                rectangle: {
                    coordinates: Cesium.Rectangle.fromDegrees(w, s, e, n),
                    material: Cesium.Color.fromCssColorString("#111111").withAlpha(1.0),
                    outline: false,
                    height: 0,
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                },
            });
            tileEntities[r + "_" + c] = ent;
        }
    }

    viewer.entities.add({
        name: "_border",
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(WEST, SOUTH, EAST, NORTH),
            material: Cesium.Color.fromCssColorString("#ffffff").withAlpha(0.0),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.35),
            outlineWidth: 1,
            height: 0,
        },
    });

    const lastTileData = {};

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
    handler.setInputAction((click) => {
        const picked = viewer.scene.pick(click.position);
        if (!picked || !picked.id || !picked.id.name) {
            document.getElementById("tileInfo").style.display = "none";
            return;
        }
        const tid = picked.id.name;
        if (!tid.match(/^\d+_\d+$/)) { document.getElementById("tileInfo").style.display = "none"; return; }
        const [row, col] = tid.split("_").map(Number);
        const lat = NORTH - (row + 0.5) * LAT_PER_TILE;
        const lng = WEST + (col + 0.5) * LNG_PER_TILE;
        const tile = lastTileData[tid];
        if (!tile) { document.getElementById("tileInfo").style.display = "none"; return; }

        const x = click.position.x + 12;
        const y = click.position.y + 12;

        let html =
            '<div class="ti-title">Tile ' + tid + '</div>' +
            '<div><span class="ti-label">Location</span> ' + lat.toFixed(5) + ', ' + lng.toFixed(5) + '</div>' +
            '<div><span class="ti-label">Status</span> ' + tile.status + '</div>';

        if (tile.status === "mapped") {
            html += '<div><span class="ti-label">Label</span> <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' + tile.color + ';vertical-align:middle"></span> ' + (LABEL_DISPLAY[tile.final_label] || tile.final_label) + '</div>';
        }
        if (tile.observation_count > 0) {
            html += '<div><span class="ti-label">Observations</span> ' + tile.observation_count + '</div>';
        }
        if (tile.top_confidence) {
            html += '<div><span class="ti-label">Confidence</span> ' + tile.top_confidence + '</div>';
        }
        if (tile.description) {
            html += '<div style="margin-top:4px"><span class="ti-label">Description</span><br>' + tile.description + '</div>';
        }
        if (tile.structures && tile.structures.length) {
            html += '<div style="margin-top:4px"><span class="ti-label">Structures</span> ' + tile.structures.join(", ") + '</div>';
        }
        if (tile.landmarks && tile.landmarks.length) {
            html += '<div><span class="ti-label">Landmarks</span> ' + tile.landmarks.join(", ") + '</div>';
        }
        if (tile.observed_by && tile.observed_by.length) {
            html += '<div><span class="ti-label">Observed by</span> Drone ' + tile.observed_by.join(", ") + '</div>';
        }

        const el = document.getElementById("tileInfo");
        el.innerHTML = html;
        el.style.left = x + "px";
        el.style.top = y + "px";
        el.style.display = "block";
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    async function poll() {
        try {
            const resp = await fetch("/state");
            const state = await resp.json();

            for (const d of state.drones) {
                if (d.row < 0 || d.row >= GRID_SIZE || d.col < 0 || d.col >= GRID_SIZE) {
                    console.warn("Drone", d.id, "OUT OF BOUNDS at", d.row, d.col);
                }
                const lat = NORTH - (d.row + 0.5) * LAT_PER_TILE;
                const lng = WEST + (d.col + 0.5) * LNG_PER_TILE;
                droneAnim[d.id].target = Cesium.Cartesian3.fromDegrees(lng, lat, 80);
            }

            const counts = {};

            for (const [tid, tile] of Object.entries(state.tiles)) {
                const ent = tileEntities[tid];
                if (!ent) continue;

                lastTileData[tid] = tile;

                if (tile.status === "in_progress") {
                    ent.rectangle.material = Cesium.Color.fromCssColorString("#FFD700").withAlpha(0.25);
                } else if (tile.status === "mapped") {
                    ent.rectangle.material = Cesium.Color.fromCssColorString(tile.color).withAlpha(0.35);
                    const label = tile.final_label || "unknown";
                    counts[label] = (counts[label] || 0) + 1;
                } else {
                    ent.rectangle.material = Cesium.Color.fromCssColorString("#111111").withAlpha(1.0);
                }
            }

            document.getElementById("coveragePct").textContent = state.coverage.coverage_pct + "%";
            document.getElementById("mappedCount").textContent = state.coverage.mapped + "/" + state.coverage.total_tiles;
            document.getElementById("obsCount").textContent = state.coverage.total_observations;

            const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
            const brkDiv = document.getElementById("breakdown");
            brkDiv.innerHTML = "";
            for (const [label, count] of sorted) {
                const pct = (count / state.coverage.mapped * 100).toFixed(1);
                const row = document.createElement("div");
                row.className = "brk-row";
                row.innerHTML =
                    '<span class="brk-swatch" style="background:' + (TILE_COLOR_MAP[label] || "#FFFFFF") + '"></span>' +
                    '<span>' + (LABEL_DISPLAY[label] || label) + '</span>' +
                    '<span class="brk-pct">' + count + ' (' + pct + '%)</span>';
                brkDiv.appendChild(row);
            }

            if (state.simulation_complete) {
                document.getElementById("complete").style.display = "block";
                const top = sorted.length ? sorted[0] : null;
                let detail = state.coverage.mapped + " tiles mapped, " + state.coverage.total_observations + " total observations";
                if (top) {
                    const topLabel = LABEL_DISPLAY[top[0]] || top[0];
                    const topPct = (top[1] / state.coverage.mapped * 100).toFixed(1);
                    detail += "<br>Most common: " + topLabel + " (" + topPct + "%)";
                }
                document.getElementById("finalStats").innerHTML = detail;
            }
        } catch (e) { /* server not ready yet */ }
    }

    setInterval(poll, 1000);
    poll();
}

function downloadJSON() {
    const a = document.createElement("a");
    a.href = "/export";
    a.download = "hivemind-map.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function downloadPNG() {
    const canvas = viewer.scene.canvas;
    const w = canvas.width, h = canvas.height;
    canvas.width = 1920;
    canvas.height = 1920;
    viewer.resize();
    const dataUrl = canvas.toDataURL("image/png");
    canvas.width = w;
    canvas.height = h;
    viewer.resize();
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = "hivemind-map.png";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

init().catch(console.error);
