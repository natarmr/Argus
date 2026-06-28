const NORTH = 40.7130;
const SOUTH = 40.7000;
const WEST = -74.0200;
const EAST = -74.0050;
const GRID_SIZE = 10;
const LAT_PER_TILE = (NORTH - SOUTH) / GRID_SIZE;
const LNG_PER_TILE = (EAST - WEST) / GRID_SIZE;

const COLOR_MAP = {
    residential: Cesium.Color.fromCssColorString("#2196F3"),
    commercial: Cesium.Color.fromCssColorString("#FF8C00"),
    industrial: Cesium.Color.fromCssColorString("#9E9E9E"),
    green_space: Cesium.Color.fromCssColorString("#4CAF50"),
    water: Cesium.Color.fromCssColorString("#00BCD4"),
    infrastructure: Cesium.Color.fromCssColorString("#FFEB3B"),
    unknown: Cesium.Color.fromCssColorString("#FFFFFF"),
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

    const droneMarkers = [];
    for (let i = 0; i < 10; i++) {
        const marker = viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(-74.01, 40.705, 50),
            point: { pixelSize: 10, color: Cesium.Color.YELLOW, outlineColor: Cesium.Color.BLACK, outlineWidth: 1 },
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
    }

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
                    material: Cesium.Color.GRAY.withAlpha(0.0),
                    outline: true,
                    outlineColor: Cesium.Color.WHITE.withAlpha(0.12),
                    outlineWidth: 1,
                    height: 0,
                },
            });
            tileEntities[r + "_" + c] = ent;
        }
    }

    async function poll() {
        try {
            const resp = await fetch("/state");
            const state = await resp.json();

            for (const d of state.drones) {
                const lat = NORTH - (d.row + 0.5) * LAT_PER_TILE;
                const lng = WEST + (d.col + 0.5) * LNG_PER_TILE;
                droneMarkers[d.id].position = Cesium.Cartesian3.fromDegrees(lng, lat, 50);
            }

            for (const [tid, tile] of Object.entries(state.tiles)) {
                const ent = tileEntities[tid];
                if (!ent) continue;
                let color;
                if (tile.status === "unexplored") {
                    color = Cesium.Color.fromCssColorString("#444444").withAlpha(0.5);
                } else if (tile.status === "in_progress") {
                    color = Cesium.Color.fromCssColorString("#FFD700").withAlpha(0.35);
                } else {
                    color = (COLOR_MAP[tile.final_label] || COLOR_MAP.unknown).withAlpha(0.5);
                }
                ent.rectangle.material = color;
            }

            document.getElementById("coveragePct").textContent = state.coverage.coverage_pct + "%";
            document.getElementById("mappedCount").textContent = state.coverage.mapped + "/" + state.coverage.total_tiles;
            document.getElementById("obsCount").textContent = state.coverage.total_observations;
        } catch (e) { /* server not ready yet */ }
    }

    setInterval(poll, 1000);
    poll();
}

init().catch(console.error);
