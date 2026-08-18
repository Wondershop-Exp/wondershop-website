"""
Instagram feed integration (2026-08-18, per Shruti — "let's fix instagram
with meta's free api now") — pulls the account's own recent media via
Meta's Instagram API with Instagram Login (graph.instagram.com, free, no
usage fee), caches it in the DB, and serves it to the frontend as fast
static JSON. This replaces:
  - the paid Elfsight widget on builder.html
  - the hardcoded 6-photo grid on index.html

One-time setup Shruti does herself in Meta's dashboards (can't be done from
here — it requires her to log into her own Instagram/Facebook accounts):
  1. Instagram account converted to a Business or Creator (professional)
     account.
  2. A Meta Developer app (developers.facebook.com) with the "Instagram
     API setup with Instagram Login" product added.
  3. Complete the Instagram Login flow once to get a short-lived user
     token, then exchange it for a long-lived one (60-day) — Meta's setup
     flow walks through this and gives you the long-lived token directly.
  4. Set IG_ACCESS_TOKEN (and optionally IG_USER_ID) in Railway's env
     vars. This file takes over refreshing the token from there — no app
     secret is needed for routine refreshes, only for that one-time
     exchange in step 3.

Design notes:
  - media_url/thumbnail_url returned by Instagram are signed CDN links that
    expire after a while, which is why this re-fetches every CACHE_TTL
    rather than caching indefinitely.
  - Every code path falls back to whatever's cached (even if stale) rather
    than raising, so a bad moment from Instagram's API or an unset/expired
    token never breaks the section — the frontend just keeps showing
    whatever it last successfully fetched (or its own static fallback if
    nothing's ever been cached yet).
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter

from config import settings
from database import database

logger = logging.getLogger(__name__)
router = APIRouter()

GRAPH_BASE = "https://graph.instagram.com"
REFRESH_BEFORE_EXPIRY = timedelta(days=10)   # 60-day token — refresh with room to spare
CACHE_TTL = timedelta(hours=3)               # how often to re-pull media from Instagram


async def _get_row():
    return await database.fetch_one("SELECT * FROM instagram_cache WHERE id = 1")


async def _save_token(token: str, expires_at: datetime):
    await database.execute(
        """
        UPDATE instagram_cache
        SET access_token = :token, token_expires_at = :expires_at, updated_on = NOW()
        WHERE id = 1
        """,
        values={"token": token, "expires_at": expires_at},
    )


async def _save_media(media_json: str):
    await database.execute(
        """
        UPDATE instagram_cache
        SET media_json = :media_json, fetched_at = NOW(), updated_on = NOW()
        WHERE id = 1
        """,
        values={"media_json": media_json},
    )


async def _save_profile(profile_json: str):
    await database.execute(
        "UPDATE instagram_cache SET profile_json = :profile_json, updated_on = NOW() WHERE id = 1",
        values={"profile_json": profile_json},
    )


async def _current_token(row):
    """The freshest known token: whatever's in the DB if we've ever
    refreshed one, else the seed value from Railway env vars."""
    if row and row["access_token"]:
        return row["access_token"], row["token_expires_at"]
    return (settings.IG_ACCESS_TOKEN or None), None


async def _refresh_token_if_needed(token: str, expires_at):
    needs_refresh = expires_at is None or (
        expires_at - datetime.now(timezone.utc) < REFRESH_BEFORE_EXPIRY
    )
    if not needs_refresh:
        return token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{GRAPH_BASE}/refresh_access_token",
                params={"grant_type": "ig_refresh_token", "access_token": token},
            )
            r.raise_for_status()
            data = r.json()
        new_token = data["access_token"]
        new_expires = datetime.now(timezone.utc) + timedelta(
            seconds=data.get("expires_in", 60 * 24 * 3600)
        )
        await _save_token(new_token, new_expires)
        logger.info("Instagram access token refreshed, new expiry %s", new_expires)
        return new_token
    except Exception:
        logger.exception("Instagram token refresh failed — keeping existing token")
        return token


async def _fetch_media(token: str, limit: int):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{GRAPH_BASE}/me/media",
            params={
                "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
                "access_token": token,
                "limit": limit,
            },
        )
        r.raise_for_status()
        return r.json().get("data", [])


async def _fetch_profile(token: str):
    """media_count/followers_count/follows_count for the live Posts/
    Followers/Following numbers on the profile card. Kept separate from
    _fetch_media so one endpoint failing doesn't take the other down with
    it — see get_instagram_feed, which tries each independently."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{GRAPH_BASE}/me",
            params={
                "fields": "username,media_count,followers_count,follows_count",
                "access_token": token,
            },
        )
        r.raise_for_status()
        return r.json()


def _cached_posts(row, limit: int):
    if row and row["media_json"]:
        return json.loads(row["media_json"])[:limit]
    return []


def _cached_profile(row):
    if row and row["profile_json"]:
        return json.loads(row["profile_json"])
    return None


@router.get("/feed")
async def get_instagram_feed(limit: int = 6):
    """
    Returns the account's latest posts. Cached in the DB and re-pulled at
    most once every few hours, so page loads never wait on Instagram's API
    and stay well inside its rate limits.
    """
    row = await _get_row()
    is_stale = (
        not row
        or not row["fetched_at"]
        or datetime.now(timezone.utc) - row["fetched_at"] > CACHE_TTL
    )
    if not is_stale:
        return {"posts": _cached_posts(row, limit), "profile": _cached_profile(row), "cached": True}

    token, expires_at = await _current_token(row)
    if not token:
        # Not configured yet (IG_ACCESS_TOKEN never set) — frontend should
        # just fall back to its own static content.
        return {
            "posts": _cached_posts(row, limit),
            "profile": _cached_profile(row),
            "cached": True,
            "configured": False,
        }

    token = await _refresh_token_if_needed(token, expires_at)

    # Media and profile are fetched and saved independently — if one call
    # fails (or Instagram's profile fields ever change), the other still
    # updates rather than the whole endpoint falling back to fully-stale
    # data.
    media = None
    try:
        media = await _fetch_media(token, limit=max(limit, 6))
        await _save_media(json.dumps(media))
    except Exception:
        logger.exception("Instagram media fetch failed — serving cached posts")

    profile = None
    try:
        profile = await _fetch_profile(token)
        await _save_profile(json.dumps(profile))
    except Exception:
        logger.exception("Instagram profile fetch failed — serving cached profile")

    return {
        "posts": media[:limit] if media is not None else _cached_posts(row, limit),
        "profile": profile or _cached_profile(row),
        "cached": media is None,
        "error": media is None,
    }
