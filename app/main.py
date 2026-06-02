from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.admin import router as admin_router
from app.auth import initialize_firebase
from app.config import get_cors_origins, get_settings
from app.db import close_pool, open_pool
from app.ingest import router as ingest_router
from app.trails import router as trails_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    initialize_firebase(settings)
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="Waymark API",
    description="GIS data API for hiking trails and outdoor applications.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
cors_origins = get_cors_origins(settings)
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "waymark-api"}


@app.get("/map", include_in_schema=False)
def map_viewer() -> FileResponse:
    return FileResponse("app/static/map.html")


@app.get("/admin", include_in_schema=False)
def admin_dashboard() -> FileResponse:
    return FileResponse("app/static/admin.html")


app.include_router(admin_router)
app.include_router(trails_router)
app.include_router(ingest_router)
