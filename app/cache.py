from datetime import UTC, datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row


def source_for_request(provider: str, state: str | None, bbox: str | None) -> str:
    if provider == "osm":
        if state:
            return f"osm-overpass-{state.lower()}"
        return "osm-overpass-bbox"

    if provider == "nps":
        return "nps-public-trails-all"

    return provider


def cache_key(provider: str, source: str, state: str | None, bbox: str | None) -> str:
    return "|".join([provider, source, state or "", bbox or ""])


def get_cache_entry(
    conn: Connection,
    *,
    provider: str,
    source: str,
    state: str | None,
    bbox: str | None,
) -> dict | None:
    sql = """
        SELECT *
        FROM trail_cache_entries
        WHERE cache_key = %(cache_key)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            {
                "cache_key": cache_key(provider, source, state, bbox),
            },
        )
        return cur.fetchone()


def is_fresh(entry: dict | None) -> bool:
    if not entry:
        return False
    if entry["status"] != "fresh":
        return False
    if not entry["expires_at"]:
        return True

    return entry["expires_at"] > datetime.now(UTC)


def mark_cache_fetching(
    conn: Connection,
    *,
    provider: str,
    source: str,
    state: str | None,
    bbox: str | None,
) -> None:
    sql = """
        INSERT INTO trail_cache_entries (
            cache_key,
            provider,
            source,
            state,
            bbox,
            status,
            updated_at
        )
        VALUES (
            %(cache_key)s,
            %(provider)s,
            %(source)s,
            %(state)s,
            %(bbox)s,
            'fetching',
            now()
        )
        ON CONFLICT (cache_key)
        DO UPDATE SET
            status = 'fetching',
            error = NULL,
            updated_at = now()
    """
    conn.execute(
        sql,
        {
            "cache_key": cache_key(provider, source, state, bbox),
            "provider": provider,
            "source": source,
            "state": state,
            "bbox": bbox,
        },
    )


def mark_cache_fresh(
    conn: Connection,
    *,
    provider: str,
    source: str,
    state: str | None,
    bbox: str | None,
    feature_count: int,
    ttl_days: int = 14,
) -> None:
    sql = """
        UPDATE trail_cache_entries
        SET
            status = 'fresh',
            feature_count = %(feature_count)s,
            error = NULL,
            fetched_at = now(),
            expires_at = now() + %(ttl)s,
            updated_at = now()
        WHERE provider = %(provider)s
          AND cache_key = %(cache_key)s
    """
    conn.execute(
        sql,
        {
            "cache_key": cache_key(provider, source, state, bbox),
            "provider": provider,
            "feature_count": feature_count,
            "ttl": timedelta(days=ttl_days),
        },
    )


def mark_cache_failed(
    conn: Connection,
    *,
    provider: str,
    source: str,
    state: str | None,
    bbox: str | None,
    error: str,
) -> None:
    sql = """
        UPDATE trail_cache_entries
        SET
            status = 'failed',
            error = %(error)s,
            updated_at = now()
        WHERE provider = %(provider)s
          AND cache_key = %(cache_key)s
    """
    conn.execute(
        sql,
        {
            "cache_key": cache_key(provider, source, state, bbox),
            "provider": provider,
            "error": error,
        },
    )
