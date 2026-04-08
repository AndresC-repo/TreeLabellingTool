import asyncio
import shutil
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import config
from routers import files
from routers import patches
from routers import view

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    async def _cleanup_old_sessions():
        while True:
            await asyncio.sleep(3600)  # hourly
            cutoff = time.time() - 86400  # 24 hours
            try:
                for session_dir in config.SESSIONS_DIR.iterdir():
                    if session_dir.is_dir() and session_dir.stat().st_mtime < cutoff:
                        shutil.rmtree(session_dir, ignore_errors=True)
            except Exception:
                pass  # don't crash the cleanup loop

    asyncio.create_task(_cleanup_old_sessions())
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
app.include_router(patches.router)

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
