# Tree Labelling Tool

A web-based point cloud labelling tool for `.las` and `.laz` files. Upload a USGS tile, cut patches in a 2D top-down view, label individual trees in a 3D viewer (with NN inference and crown segmentation to help), and save the labelled patches as training data. A dataset overview page keeps track of what has been labelled.

---

## Quick start (for labellers)

You only need **Docker Desktop** and **git**. Works on Windows, macOS and Linux.

**1. Install**
- Docker Desktop: https://www.docker.com/products/docker-desktop/ — start it once and leave it running.
  On Windows, accept the WSL 2 setup if it asks.
- git: https://git-scm.com/downloads (macOS: run `git --version` in Terminal and accept the install).

Your computer needs about **10 GB free disk space** and **8 GB RAM** (16 GB recommended).

**2. Download the tool** (in a terminal: PowerShell on Windows, Terminal on macOS)

```bash
git clone https://github.com/AndresC-repo/TreeLabellingTool.git
cd TreeLabellingTool
```

**3. Personal settings** — copy the template and put your initials in it:

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` in any text editor and set `LABELLER=` to your initials (e.g. `LABELLER=MK`).
They are added to every file you save, so labels from different people never clash.

**4. Start**

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first start downloads and builds everything (10–20 minutes). Later starts take seconds.
Then open **http://localhost:8080** in your browser.

**5. Your labels** are saved in the `data/labels` folder inside the tool folder
(set `DATASET_DIR_HOST` in `.env` to use another folder). The **📊 Dataset** page lists everything you
labelled; `data/labelling_registry.json` holds that list. Send the `data` folder (or the `.las` files in
`data/labels`) to whoever collects the training data.

**Everyday commands** (run in the tool folder)

| What | Command |
|---|---|
| Stop the tool | `docker compose -f docker-compose.prod.yml down` |
| Start it again | `docker compose -f docker-compose.prod.yml up -d` |
| Update to the newest version | `git pull` then `docker compose -f docker-compose.prod.yml up -d --build` |
| See errors | `docker compose -f docker-compose.prod.yml logs -f backend` |

**Notes**
- **Apple Silicon Macs (M1–M4):** the backend runs through Docker's Intel emulation. Everything works,
  but NN inference is slower. In Docker Desktop → Settings → General, keep
  "Use Rosetta for x86_64/amd64 emulation" switched on.
- **Port 8080 already in use?** Set `PORT=8090` (or any free port) in `.env` and open that port instead.
- The NN models are downloaded from Hugging Face the first time you run inference (internet needed once).
  If the model repository is private, put a read token in `.env` as `HF_TOKEN=…`.
- `docker compose ... down` keeps your uploaded files; your saved labels are in `data/labels` and are never
  touched by Docker commands.

---

## Features

- **File upload** — drag-and-drop or browse for `.las` / `.laz` files up to 2 GB; units (metres / US feet) detected from the CRS, with a warning when they can only be guessed
- **2D top-down view** — scalar fields (elevation, classification, intensity, returns); cut patches with rectangle, polygon or fixed-size rectangle; patches stay outlined and numbered
- **3D patch viewer** — orbit/pan/zoom, point size, elevation filter, clipping, keyboard shortcuts
- **Labelling** — screen-space lasso, tree IDs from 101 upwards, protect ground/building, replace a label inside a selection; **undo/redo up to 200 steps**
- **NN inference** — SegmentAnyTree models (tree / non-tree), downloaded from Hugging Face
- **Tree instance segmentation** — CHM watershed (min height, min peak height) with Optuna auto-tune
- **Save** — writes `<City>_<tile>_p<n>_<labeller>_t<trees>.las` straight into the training labels folder; real ASPRS classes + exact labels in a `label` field + units marker
- **Dataset overview** — all patches and source tiles with tree counts, regions, status and notes; double-click to reopen a patch, rename files, CSV export

---

## Development

Hot reload for backend and frontend:

```bash
docker compose up --build        # or: make dev-build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (docs at /docs)

| Command | Description |
|---|---|
| `make dev` / `make dev-build` | Dev stack (hot reload), optionally rebuilding images |
| `make prod` / `make prod-build` | Labelling stack on http://localhost:8080 |
| `make logs`, `make logs-backend`, `make logs-frontend` | Tail logs |
| `make down` | Stop containers (uploaded files are kept) |
| `make clean` | Stop containers and delete uploaded files and cached models |

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `LABELLER` | *(empty)* | Your initials; added to saved file names and shown on the dataset page |
| `DATASET_DIR_HOST` | `./data` | Folder on your computer for `labels/` and `labelling_registry.json` |
| `PORT` | `8080` | Port of the labelling stack |
| `HF_TOKEN` | *(empty)* | Hugging Face token, only if the model repository is private |
| `MAX_UPLOAD_BYTES` | `2147483648` | Upload limit (2 GB) |
| `DEFAULT_MAX_POINTS` | `500000` | Points drawn in the 2D view |

Uploaded files and patches live in a Docker volume (`storage_data`) and are removed after 24 h without use.
Downloaded models are cached in the `hf_cache` volume.

---

## Project Structure

```
.
├── backend/
│   ├── main.py                    # FastAPI app, lifespan, session cleanup
│   ├── config.py                  # Storage paths, size limits
│   ├── routers/
│   │   ├── files.py               # Upload and session info endpoints
│   │   ├── dataset.py             # Dataset overview: list, scan, edit, open, rename, CSV
│   │   ├── view.py                # 2D binary buffer and colormap endpoints
│   │   └── patches.py             # Extract, label, relabel, save, predict, segment, auto-tune, training
│   ├── models/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── services/
│   │   ├── las_reader.py          # Session management, metadata extraction
│   │   ├── decimator.py           # Stride-based point decimation
│   │   ├── projection.py          # Scalar field → RGB colour mapping
│   │   ├── renderer2d.py          # Server-side 2D image rendering
│   │   ├── patch_extractor.py     # Polygon PIP extraction, patch writing
│   │   ├── label_manager.py       # In-memory label state per patch (undo/redo)
│   │   ├── dataset_registry.py    # labelling_registry.json: tiles, patches, statuses
│   │   ├── las_writer.py          # Write labelled patch to .las
│   │   ├── point_cache.py         # LRU cache for loaded point arrays
│   │   ├── predictor.py           # SegmentAnyTree NN inference (5 model variants)
│   │   ├── segment_any_tree.py    # spconv model definition
│   │   ├── tree_segmentor.py      # CHM watershed crown delineation
│   │   ├── tree_metrics.py        # Per-tree height / crown metrics
│   │   ├── seg_quality.py         # Geometric quality score for auto-tune
│   │   ├── seg_autotuner.py       # Optuna hyperparameter search (geometric + supervised ARI)
│   │   └── training_store.py      # Save/load ground-truth training examples
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── UploadView.vue         # File upload page
│   │   │   ├── View2D.vue             # 2D top-down viewer
│   │   │   ├── DatasetView.vue        # Dataset overview page
│   │   │   └── PatchView3D.vue        # 3D viewer orchestration + keyboard shortcuts
│   │   ├── components/
│   │   │   ├── upload/DropZone.vue
│   │   │   ├── view2d/                # CanvasRenderer2D, selection overlays
│   │   │   └── patch3d/
│   │   │       ├── CanvasRenderer3D.vue   # Three.js scene, lasso, view-mode switching
│   │   │       ├── LassoOverlay.vue       # SVG lasso drawing layer
│   │   │       ├── ElevationFilter.vue    # Z-range slider
│   │   │       ├── LabelPanel.vue         # Label controls + replace-in-selection
│   │   │       ├── PatchLegend.vue        # Classification colour legend + training save
│   │   │       ├── InferenceLegend.vue    # Inference results, segmentation controls, auto-tune
│   │   │       └── SavePanel.vue          # Save / download panel
│   │   ├── composables/
│   │   │   ├── useThreeScene.js           # Shared Three.js scene/camera/renderer
│   │   │   ├── usePointCloud3D.js         # 3D point cloud load, colours, label access
│   │   │   ├── usePointCloud2D.js         # 2D point cloud load + buffer management
│   │   │   ├── useScalarColors.js         # Scalar field → colour mapping (frontend)
│   │   │   ├── useSelectionRect.js        # Rectangle drag selection
│   │   │   ├── useSelectionFreehand.js    # Polygon click selection
│   │   │   ├── useFixedRect.js            # Draw-once, draggable rectangle
│   │   │   └── useLasso3D.js              # Screen-space lasso + Web Worker dispatch
│   │   ├── stores/
│   │   │   ├── session.js                 # Uploaded file session state
│   │   │   ├── view2d.js                  # Active tool, scalar field, labelled regions
│   │   │   └── patch3d.js                 # Patch state, inference results, lasso, view mode
│   │   └── workers/
│   │       └── pointInPolygon.worker.js   # MVP projection + ray-cast PIP (off-thread)
│   ├── nginx.conf
│   └── Dockerfile
│
├── docker-compose.yml             # Development stack (hot reload)
├── docker-compose.prod.yml        # Labelling stack (nginx, port 8080)
├── .env.example                   # Personal settings template → copy to .env
└── Makefile
```

---

## How It Works

### Labelling workflow
1. **Upload** a `.las` or `.laz` file. The backend creates a session directory and stores the file.
2. **2D view** — the file is decimated (up to 500 k points by default) and streamed as a binary Float32 buffer. Three.js renders it as an orthographic top-down scatter plot coloured by the chosen scalar field.
3. **Select a patch** — draw a rectangle, polygon, or fixed rectangle over the 2D view (or use "Whole Patch" to load the entire file). The backend extracts only the points inside that region into a patch file.
4. **3D view** — the patch is streamed as an 8-float-per-point buffer (`x y z r g b current_label orig_classification`) and rendered with a perspective camera.
5. **Lasso** — draw a freehand lasso over the 3D view. A Web Worker projects all points through the MVP matrix into screen space and runs a ray-casting point-in-polygon test to find matching indices.
6. **Label** — assign a numeric label to the selected points (starts at 101, auto-increments). Use **Replace in Selection** to relabel only points currently carrying a specific label within the lasso, leaving all others untouched.
7. **Save** — the backend writes a new `.las` file with a custom `label` dimension storing the assigned values. A download link is returned.

### Inference & segmentation workflow
1. **Run Inference** (`I` key or button) — the backend loads the SegmentAnyTree model (downloaded from HuggingFace on first use), voxelizes the patch at 0.1 m, and returns per-point semantic labels: `0` = non-tree, `101` = tree.
2. **Segment Trees** — a CHM is rasterized from tree points and smoothed (Duncanson 2014). Local maxima are used as watershed seeds; each crown segment becomes an instance label (201, 202, …).
3. **Auto-tune** — Optuna searches 8 segmentation hyperparameters. Objective is a geometric quality score (coverage × compactness × crown area) unless supervised training examples exist, in which case it maximises mean Adjusted Rand Index across saved examples.
4. **Save as Training Example** — stores the corrected segmentation (point coordinates + semantic + instance labels) in `storage/training/`. Future auto-tune runs use these as ground truth.
5. **Apply to Labels** — bulk-applies the instance labels to the patch's persistent label state, which is written to the `.las` file on save.

---

## Keyboard Shortcuts (3D viewer)

| Key | Action |
|---|---|
| `R` | Toggle auto-rotate |
| `S` | Side view |
| `T` | Top view |
| `V` | Cycle view mode |
| `L` | Classification view |
| `I` | Run inference |
| `Enter` / `Space` | Apply current label to selection |
| `G` | Apply ground label to selection |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+S` | Save patch |

---

## Inference Models

Downloaded automatically from Hugging Face (`AndCarr/UrbanTreeDetector`) on first use.

| Model | Input | File |
|---|---|---|
| Metric | XYZ in metres (converted automatically from feet) | `best_model_m.pth` |
| Finetune | XYZ | `best_model.pth` |
| Finetune + intensity | XYZ + intensity | `best_model_int.pth` |
| Scratch | XYZ | `best_model_scratch.pth` |
| Scratch + intensity | XYZ + intensity | `best_model_scratch_int.pth` |
