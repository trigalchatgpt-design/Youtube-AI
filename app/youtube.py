from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_states: dict[str, float] = {}
_ephemeral_refresh_token: str | None = None


def _client_id() -> str:
    return os.getenv("YOUTUBE_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.getenv(
        "YOUTUBE_REDIRECT_URI",
        "https://youtube-ai-prod-production.up.railway.app/oauth/youtube/callback",
    ).strip()


def oauth_configured() -> bool:
    return bool(_client_id() and _client_secret())


def connected() -> bool:
    return bool(os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip() or _ephemeral_refresh_token)


def authorization_url() -> str:
    if not oauth_configured():
        raise RuntimeError("YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are required")
    state = secrets.token_urlsafe(32)
    _states[state] = time.time() + 900
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, state: str) -> dict:
    global _ephemeral_refresh_token
    expires = _states.pop(state, 0)
    if not expires or expires < time.time():
        raise RuntimeError("OAuth state is invalid or expired")
    response = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    refresh = data.get("refresh_token")
    if refresh:
        _ephemeral_refresh_token = refresh
    return {
        "access_token": data.get("access_token"),
        "refresh_token": refresh,
        "scope": data.get("scope"),
        "expires_in": data.get("expires_in"),
    }


def _refresh_token() -> str:
    token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip() or _ephemeral_refresh_token
    if not token:
        raise RuntimeError("YouTube is not connected")
    return token


def access_token() -> str:
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "refresh_token": _refresh_token(),
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def channel_info() -> dict:
    token = access_token()
    response = httpx.get(
        f"{YOUTUBE_API}/channels",
        params={"part": "snippet,statistics,contentDetails", "mine": "true"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def uploads_playlist_id() -> str:
    data = channel_info()
    items = data.get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel is connected")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def find_uploaded_video_by_title(title: str, max_items: int = 100) -> dict | None:
    token = access_token()
    playlist_id = uploads_playlist_id()
    page_token: str | None = None
    seen = 0
    while seen < max_items:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_items - seen),
        }
        if page_token:
            params["pageToken"] = page_token
        response = httpx.get(
            f"{YOUTUBE_API}/playlistItems",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        for item in data.get("items", []):
            if item.get("snippet", {}).get("title", "").strip() == title.strip():
                return {
                    "video_id": item.get("contentDetails", {}).get("videoId"),
                    "title": item.get("snippet", {}).get("title"),
                }
        batch = len(data.get("items", []))
        seen += batch
        page_token = data.get("nextPageToken")
        if not page_token or batch == 0:
            break
    return None


def upload_video(video_path: Path, title: str, description: str, tags: list[str] | None = None, privacy_status: str = "private", category_id: str = "27") -> dict:
    token = access_token()
    size = video_path.stat().st_size
    metadata = {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": (tags or [])[:500], "categoryId": category_id},
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    start = httpx.post(
        f"{YOUTUBE_UPLOAD}/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        json=metadata,
        timeout=60,
    )
    start.raise_for_status()
    location = start.headers.get("Location")
    if not location:
        raise RuntimeError("YouTube did not return a resumable upload URL")
    with video_path.open("rb") as handle:
        upload = httpx.put(location, headers={"Content-Type": "video/mp4", "Content-Length": str(size)}, content=handle, timeout=None)
    upload.raise_for_status()
    return upload.json()


def set_thumbnail(video_id: str, thumbnail_path: Path) -> dict:
    token = access_token()
    mime = "image/png" if thumbnail_path.suffix.lower() == ".png" else "image/jpeg"
    response = httpx.post(
        f"{YOUTUBE_UPLOAD}/thumbnails/set",
        params={"videoId": video_id, "uploadType": "media"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": mime},
        content=thumbnail_path.read_bytes(),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()
