.PHONY: help dev dev-build prod prod-build down logs logs-backend logs-frontend clean

# Default target
.DEFAULT_GOAL := help

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Point Cloud Labeling Tool"
	@echo ""
	@echo "Usage: make <command>"
	@echo ""
	@echo "Development:"
	@echo "  dev           Start dev stack (hot-reload backend + Vite frontend)"
	@echo "  dev-build     Rebuild images before starting dev stack"
	@echo ""
	@echo "Production:"
	@echo "  prod          Start prod stack (nginx-served frontend, no --reload)"
	@echo "  prod-build    Rebuild images before starting prod stack"
	@echo ""
	@echo "Logs:"
	@echo "  logs          Tail logs from all containers"
	@echo "  logs-backend  Tail backend logs only"
	@echo "  logs-frontend Tail frontend logs only"
	@echo ""
	@echo "Teardown:"
	@echo "  down          Stop and remove containers (keeps volumes)"
	@echo "  clean         Stop containers and remove volumes (deletes all uploaded files)"
	@echo ""

# ─── Development ─────────────────────────────────────────────────────────────

# Starts both services with source-mounted volumes so changes are reflected
# immediately. Backend uses uvicorn --reload; frontend uses Vite dev server.
# Access: http://localhost:5173 (frontend), http://localhost:8000 (backend API)
dev:
	docker compose up

dev-build:
	docker compose up --build

# ─── Production ──────────────────────────────────────────────────────────────

# Builds the frontend with `npm run build` and serves it via nginx on port 80.
# Backend runs without --reload. Storage is persisted in a named Docker volume.
# Access: http://localhost (port 80)
prod:
	docker compose -f docker-compose.prod.yml up

prod-build:
	docker compose -f docker-compose.prod.yml up --build

# ─── Logs ────────────────────────────────────────────────────────────────────

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

# ─── Teardown ────────────────────────────────────────────────────────────────

# Stops containers but keeps the storage_data volume intact.
down:
	docker compose down

# Stops containers AND removes the storage_data volume.
# WARNING: this deletes all uploaded .las files and session data.
clean:
	docker compose down -v
