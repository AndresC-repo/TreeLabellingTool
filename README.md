# Tree Labelling Tool

A web-based point cloud labelling tool for `.las` and `.laz` files. Upload a file, select regions in a 2D top-down view, inspect them in a 3D viewer, run neural-network tree detection, segment individual crowns, assign labels, and download the result as a new `.las` file.

---

## Features

- **File upload** — drag-and-drop or browse for `.las` / `.laz` files up to 2 GB
- **2D top-down view** — orthographic Z-projection with scalar field switching (elevation, classification, intensity, number of returns)
- **Three selection tools**
  - Rectangle drag
  - Freehand polygon (click to add points, right-click to close)
  - Fixed rectangle (draw once, drag to reposition)
- **Whole-patch mode** — load the entire LAS file into the 3D viewer without drawing a selection
- **3D patch viewer** — perspective view with OrbitControls (orbit, pan, zoom); point-size controls; elevation filter slider; keyboard shortcuts
- **View modes** — cycle between elevation, classification, DTM, CHM, prediction, and inference-CHM colour schemes (`V` key)
- **Screen-space lasso** — draw a freehand lasso over the 3D view; point-in-polygon is computed off the main thread via a Web Worker
- **Label assignment** — incrementing labels starting at 101; apply to selected points, auto-advances to next label; protect ground/building classes (ASPRS 2/6)
- **Replace label in selection** — within a lasso selection replace only points with label X → Y, leaving all other labels untouched
- **NN inference** — run a SegmentAnyTree model (4 variants) to classify points as tree / non-tree; results shown in a prediction colour scheme
- **Tree instance segmentation** — CHM-based crown delineation (Duncanson 2014 watershed algorithm) with tunable parameters
- **Auto-tune segmentation** — Optuna hyperparameter search; geometric quality score (geometric mode) or Adjusted Rand Index against user-corrected examples (supervised mode)
- **Supervised training examples** — save a corrected patch segmentation as ground truth; subsequent auto-tune runs use mean ARI across all saved examples
- **Export** — save the labelled patch as a `.las` file and download it; auto-generated filename encodes label IDs and tree count

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.9, FastAPI, laspy, NumPy, SciPy, scikit-image |
| Inference | PyTorch (CPU), MinkowskiEngine, HuggingFace Hub |
| Segmentation | scikit-image watershed, Optuna, scikit-learn (ARI) |
| Frontend | Vue 3, Three.js, Pinia, Vue Router 4, Axios |
| Containerisation | Docker, docker-compose, Nginx |

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

### Development

Hot-reload on both backend and frontend:

```bash
make dev
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

### Production

Optimised build served via Nginx on port 80:

```bash
make prod
```

- App: http://localhost

---

## Makefile Commands

| Command | Description |
|---|---|
| `make dev` | Start dev stack (hot-reload backend + Vite frontend) |
| `make dev-build` | Rebuild images, then start dev stack |
| `make prod` | Start prod stack (Nginx-served frontend, no `--reload`) |
| `make prod-build` | Rebuild images, then start prod stack |
| `make logs` | Tail logs from all containers |
| `make logs-backend` | Tail backend logs only |
| `make logs-frontend` | Tail frontend logs only |
| `make down` | Stop containers (uploaded files are preserved) |
| `make clean` | Stop containers and delete all uploaded files |

---

## Project Structure

```
.
├── backend/
│   ├── main.py                    # FastAPI app, lifespan, session cleanup
│   ├── config.py                  # Storage paths, size limits
│   ├── routers/
│   │   ├── files.py               # Upload and session info endpoints
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
│   │   ├── label_manager.py       # In-memory label state per patch
│   │   ├── las_writer.py          # Write labelled patch to .las
│   │   ├── point_cache.py         # LRU cache for loaded point arrays
│   │   ├── predictor.py           # SegmentAnyTree NN inference (v1–v4)
│   │   ├── segment_any_tree.py    # MinkowskiEngine model definition
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
├── docker-compose.yml             # Development stack
├── docker-compose.prod.yml        # Production stack
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
| `V` | Cycle view mode (elevation / DTM / CHM or prediction / DTM / inference-CHM) |
| `L` | Classification view |
| `I` | Run inference (v1) |
| `Enter` / `Space` | Apply current label to selection |
| `G` | Apply ground label to selection |
| `Ctrl+S` | Save patch |

---

## Inference Models

Models are downloaded automatically from HuggingFace (`AndCarr/UrbanTreeDetector`) on first use.

| Version | Input features | Model file |
|---|---|---|
| v1 | XYZ | `best_model.pth` |
| v2 | XYZ + Classification | `best_model_cls.pth` |
| v3 | XYZ + Intensity | `best_model_int.pth` |
| v4 | XYZ + Intensity + Classification | `best_model_int_cls.pth` |

---

## Configuration

Key constants in `backend/config.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 2 GB | Maximum upload file size |
| `DEFAULT_MAX_POINTS` | 500 000 | Points rendered in the 2D view |
| `DECIMATION_CHUNK_SIZE` | 100 000 | Chunk size for streaming decimation |

Session data is stored in `backend/storage/sessions/` and automatically deleted after 24 hours.
Training examples are stored in `backend/storage/training/` and persist across sessions.
The Optuna study database is at `backend/storage/optuna.db`.
