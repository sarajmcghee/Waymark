from typing import Any

from fastapi import APIRouter, Depends
from psycopg import Connection
from psycopg.rows import dict_row

from app.auth import require_admin
from app.config import Settings, get_firebase_web_config, get_settings
from app.db import get_connection
from app.presets import SOURCE_PRESETS

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def stats(
    _: dict = Depends(require_admin),
    conn: Connection = Depends(get_connection),
) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT count(*) AS trail_count FROM trails")
        trail_count = cur.fetchone()["trail_count"]

        cur.execute(
            """
            SELECT source, count(*) AS trail_count
            FROM trails
            GROUP BY source
            ORDER BY trail_count DESC, source
            """
        )
        sources = cur.fetchall()

        cur.execute("SELECT count(*) AS run_count FROM ingest_runs")
        run_count = cur.fetchone()["run_count"]

    return {
        "trail_count": trail_count,
        "source_count": len(sources),
        "ingest_run_count": run_count,
        "sources": sources,
    }


@router.get("/source-presets")
def source_presets(_: dict = Depends(require_admin)) -> list[dict[str, Any]]:
    return SOURCE_PRESETS


@router.get("/firebase-config")
def firebase_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    web_config = get_firebase_web_config(settings)
    return {
        "auth_required": web_config is not None,
        "config": web_config,
    }
