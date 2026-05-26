#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path
from typing import Optional

import requests

CACHE_KEY = "pingpocket:players"
TABLE_NAME = "ping_results"
LOCAL_CACHE_PATH = Path(__file__).resolve().parent / "ping_cache.json"


def _postgres_url() -> Optional[str]:
    return (
        os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
        or os.environ.get("POSTGRES_PRISMA_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("DATABASE_URL")
    )


def _supabase_env() -> tuple[Optional[str], Optional[str]]:
    return (
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_KEY"),
    )


def _redis_env() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("KV_REST_API_URL"), os.environ.get("KV_REST_API_TOKEN")


def _redis_command(*command: str) -> object:
    url, token = _redis_env()
    if not url or not token:
        raise RuntimeError("Redis REST env vars are missing")

    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=list(command),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result")


def _connect_postgres():
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError as exc:
        raise RuntimeError("psycopg2-binary is required for Supabase/Postgres storage") from exc

    dsn = _postgres_url()
    if not dsn:
        raise RuntimeError("Postgres env var is missing")
    return psycopg2.connect(dsn, sslmode="require"), Json


def _ensure_postgres_table(cursor) -> None:
    cursor.execute(
        f"""
        create table if not exists public.{TABLE_NAME} (
            id text primary key,
            club_id text not null,
            players jsonb not null,
            updated_at timestamptz not null,
            empty_cache boolean not null default false
        )
        """
    )


def _get_postgres_results() -> Optional[dict]:
    connection, _ = _connect_postgres()
    try:
        with connection:
            with connection.cursor() as cursor:
                _ensure_postgres_table(cursor)
                cursor.execute(
                    f"""
                    select club_id, players, updated_at, empty_cache
                    from public.{TABLE_NAME}
                    where id = %s
                    """,
                    (CACHE_KEY,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                club_id, players, updated_at, empty_cache = row
                return {
                    "club_id": club_id,
                    "players": players,
                    "updated_at": updated_at.isoformat(timespec="seconds"),
                    "empty_cache": empty_cache,
                }
    finally:
        connection.close()


def _set_postgres_results(payload: dict) -> None:
    connection, Json = _connect_postgres()
    try:
        with connection:
            with connection.cursor() as cursor:
                _ensure_postgres_table(cursor)
                cursor.execute(
                    f"""
                    insert into public.{TABLE_NAME} (id, club_id, players, updated_at, empty_cache)
                    values (%s, %s, %s, %s, %s)
                    on conflict (id) do update set
                        club_id = excluded.club_id,
                        players = excluded.players,
                        updated_at = excluded.updated_at,
                        empty_cache = excluded.empty_cache
                    """,
                    (
                        CACHE_KEY,
                        payload["club_id"],
                        Json(payload["players"]),
                        payload["updated_at"],
                        payload.get("empty_cache", False),
                    ),
                )
    finally:
        connection.close()


def _supabase_rest_url(path: str) -> str:
    url, _ = _supabase_env()
    if not url:
        raise RuntimeError("SUPABASE_URL is missing")
    return f"{url.rstrip('/')}/rest/v1/{path.lstrip('/')}"


def _supabase_headers() -> dict:
    _, key = _supabase_env()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _get_supabase_rest_results() -> Optional[dict]:
    response = requests.get(
        _supabase_rest_url(f"{TABLE_NAME}?id=eq.{CACHE_KEY}&select=club_id,players,updated_at,empty_cache"),
        headers=_supabase_headers(),
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    row = rows[0]
    return {
        "club_id": row["club_id"],
        "players": row["players"],
        "updated_at": row["updated_at"],
        "empty_cache": row.get("empty_cache", False),
    }


def _set_supabase_rest_results(payload: dict) -> None:
    response = requests.post(
        _supabase_rest_url(TABLE_NAME),
        headers={
            **_supabase_headers(),
            "Prefer": "resolution=merge-duplicates",
        },
        json={
            "id": CACHE_KEY,
            "club_id": payload["club_id"],
            "players": payload["players"],
            "updated_at": payload["updated_at"],
            "empty_cache": payload.get("empty_cache", False),
        },
        timeout=30,
    )
    response.raise_for_status()


def get_cached_results() -> Optional[dict]:
    if _postgres_url():
        return _get_postgres_results()

    supabase_url, supabase_key = _supabase_env()
    if supabase_url and supabase_key:
        return _get_supabase_rest_results()

    url, token = _redis_env()
    if url and token:
        raw = _redis_command("GET", CACHE_KEY)
        return json.loads(raw) if raw else None

    if not LOCAL_CACHE_PATH.exists():
        return None
    return json.loads(LOCAL_CACHE_PATH.read_text(encoding="utf-8"))


def set_cached_results(payload: dict) -> None:
    if _postgres_url():
        _set_postgres_results(payload)
        return

    supabase_url, supabase_key = _supabase_env()
    if supabase_url and supabase_key:
        _set_supabase_rest_results(payload)
        return

    serialized = json.dumps(payload, ensure_ascii=False)
    url, token = _redis_env()
    if url and token:
        _redis_command("SET", CACHE_KEY, serialized)
        return

    LOCAL_CACHE_PATH.write_text(serialized, encoding="utf-8")
