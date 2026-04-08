from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import config
from routers import files
from routers import view

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="Point Cloud Labeling Tool", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80", "http://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router)
app.include_router(view.router)

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
