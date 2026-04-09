# Tree Labelling Tool

A web-based point cloud labelling tool for `.las` and `.laz` files. Upload a file, select regions in a 2D top-down view, inspect them in a 3D viewer, assign labels, and download the result as a new `.las` file.

---

## Features

- **File upload** — drag-and-drop or browse for `.las` / `.laz` files up to 2 GB
- **2D top-down view** — orthographic Z-projection with scalar field switching (classification, intensity, number of returns)
- **Three selection tools**
  - Rectangle drag
  - Freehand polygon (click to add points, right-click to close)
  - Fixed rectangle (draw once, drag to reposition)
- **3D patch viewer** — perspective view with OrbitControls (orbit, pan, zoom)
- **Screen-space lasso segmentation** — draw a freehand lasso over the 3D view; point-in-polygon is computed off the main thread via a Web Worker
- **Label assignment** — incrementing labels starting at 101; apply to selected points, auto-advances to the next label
- **Export** — save the labelled patch as a `.las` file and download it

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, laspy, NumPy |
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
│   ├── main.py                  # FastAPI app, lifespan, session cleanup
│   ├── config.py                # Storage paths, size limits
│   ├── routers/
│   │   ├── files.py             # Upload and session info endpoints
│   │   ├── view.py              # 2D binary buffer and colormap endpoints
│   │   └── patches.py           # Patch extract, label, save, download
│   ├── services/
│   │   ├── las_reader.py        # Session management, metadata extraction
│   │   ├── decimator.py         # Stride-based point decimation
│   │   ├── projection.py        # Scalar field → RGB colour mapping
│   │   ├── patch_extractor.py   # Polygon PIP extraction, patch writing
│   │   ├── label_manager.py     # In-memory label state per patch
│   │   └── las_writer.py        # Write labelled patch to .las
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── UploadView.vue       # File upload page
│   │   │   ├── View2D.vue           # 2D top-down viewer
│   │   │   └── PatchView3D.vue      # 3D patch viewer + label/save panels
│   │   ├── components/
│   │   │   ├── upload/DropZone.vue
│   │   │   ├── view2d/              # CanvasRenderer2D, selection overlays
│   │   │   └── patch3d/             # CanvasRenderer3D, LassoOverlay, LabelPanel, SavePanel
│   │   ├── composables/
│   │   │   ├── useThreeScene.js     # Shared Three.js scene/camera/renderer setup
│   │   │   ├── usePointCloud2D.js   # 2D point cloud load + buffer management
│   │   │   ├── usePointCloud3D.js   # 3D point cloud load, highlight, label colours
│   │   │   ├── useSelectionRect.js  # Rectangle drag selection
│   │   │   ├── useSelectionFreehand.js  # Polygon click selection
│   │   │   ├── useFixedRect.js      # Draw-once, draggable rectangle
│   │   │   └── useLasso3D.js        # Screen-space lasso + Web Worker dispatch
│   │   ├── stores/
│   │   │   ├── session.js           # Uploaded file session state
│   │   │   ├── view2d.js            # Active tool, scalar field, labelled regions
│   │   │   └── patch3d.js           # Patch state, selected indices, lasso processing
│   │   └── workers/
│   │       └── pointInPolygon.worker.js  # MVP projection + ray-cast PIP (off-thread)
│   ├── nginx.conf
│   └── Dockerfile
│
├── docker-compose.yml           # Development stack
├── docker-compose.prod.yml      # Production stack
└── Makefile
```

---

## How It Works

1. **Upload** a `.las` or `.laz` file. The backend creates a session directory and stores the file.
2. **2D view** — the file is decimated (up to 500 k points by default) and streamed as a binary Float32 buffer. Three.js renders it as an orthographic top-down scatter plot coloured by the chosen scalar field.
3. **Select a patch** — draw a rectangle, polygon, or fixed rectangle over the 2D view. The backend extracts only the points inside that polygon into a patch file.
4. **3D view** — the patch is streamed as a 7-float-per-point buffer (x, y, z, r, g, b, classification) and rendered with a perspective camera. OrbitControls allow free navigation.
5. **Lasso** — draw a freehand lasso over the 3D view. A Web Worker projects all points through the MVP matrix into screen space and runs a ray-casting point-in-polygon test to find matching indices.
6. **Label** — assign a numeric label to the selected points. Labels start at 101 and increment automatically. Applied points are recoloured in the 3D view.
7. **Save** — the backend writes a new `.las` file with the `classification` field overwritten by the assigned labels. A download link is returned.

---

## Configuration

Key constants in `backend/config.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 2 GB | Maximum upload file size |
| `DEFAULT_MAX_POINTS` | 500 000 | Points rendered in the 2D view |
| `DECIMATION_CHUNK_SIZE` | 100 000 | Chunk size for streaming decimation |

Session data is stored in `backend/storage/sessions/` and automatically deleted after 24 hours.
