import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import config
from routers import files
from routers import patches
from routers import view
from routers import dataset
from services.sessions import purge_session, touch_session, session_id_from_path

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    async def _cleanup_old_sessions():
        while True:
            await asyncio.sleep(3600)  # hourly
            cutoff = time.time() - 86400  # 24 hours since last use
            try:
                for session_dir in config.SESSIONS_DIR.iterdir():
                    # mtime is refreshed on every request touching the session (see middleware)
                    if session_dir.is_dir() and session_dir.stat().st_mtime < cutoff:
                        purge_session(session_dir.name)
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

@app.middleware("http")
async def keep_session_alive(request: Request, call_next):
    sid = session_id_from_path(request.url.path)
    # Deleting a whole file must not recreate its timestamp; everything else counts as use
    if sid and not (request.method == "DELETE" and request.url.path.startswith("/api/v1/files/")):
        touch_session(sid)
    return await call_next(request)

app.include_router(files.router)
app.include_router(view.router)
app.include_router(patches.router)
app.include_router(dataset.router)

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
