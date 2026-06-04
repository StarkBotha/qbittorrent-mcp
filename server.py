#!/usr/bin/env python3
"""MCP server for qBittorrent WebUI API."""

import json
import os
from typing import Optional
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

# Config from env vars
QBT_URL = os.environ.get("QBT_URL", "")  # e.g. http://localhost:8080 or https://qbittorrent.example.com
QBT_USER = os.environ.get("QBT_USER", "admin")  # default matches qBittorrent default; override via env
QBT_PASS = os.environ.get("QBT_PASS", "")

mcp = FastMCP("qbittorrent")


def _check_config():
    if not QBT_URL:
        raise RuntimeError(
            "QBT_URL env var is not set. Set it to your qBittorrent WebUI base URL, "
            "e.g. export QBT_URL=http://localhost:8080"
        )

# Session cookie storage
_cookie: Optional[str] = None


async def _ensure_auth() -> str:
    """Login to qBittorrent and return cookie header."""
    global _cookie
    if _cookie:
        return _cookie
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            f"{QBT_URL}/api/v2/auth/login",
            data={"username": QBT_USER, "password": QBT_PASS},
        )
        if resp.text.strip() != "Ok.":
            raise RuntimeError(f"qBittorrent login failed: {resp.text}")
        _cookie = "; ".join(f"{k}={v}" for k, v in resp.cookies.items())
        return _cookie


async def _api(method: str, endpoint: str, **kwargs) -> httpx.Response:
    """Make an authenticated API request."""
    cookie = await _ensure_auth()
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        url = f"{QBT_URL}/api/v2/{endpoint}"
        headers = {"Cookie": cookie}
        if method == "GET":
            resp = await client.get(url, headers=headers, **kwargs)
        else:
            resp = await client.post(url, headers=headers, **kwargs)
        # If unauthorized, re-auth and retry
        if resp.status_code == 403:
            global _cookie
            _cookie = None
            cookie = await _ensure_auth()
            headers["Cookie"] = cookie
            if method == "GET":
                resp = await client.get(url, headers=headers, **kwargs)
            else:
                resp = await client.post(url, headers=headers, **kwargs)
        return resp


# ── Tools ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def qbt_list_torrents(
    filter: Optional[str] = None,
    category: Optional[str] = None,
    sort: Optional[str] = None,
    reverse: Optional[bool] = None,
    search: Optional[str] = None,
) -> str:
    """List torrents in qBittorrent.

    Args:
        filter: Filter by state - all, downloading, completed, paused, active, inactive, resumed, stalled, stalled_uploading, stalled_downloading
        category: Filter by category name
        sort: Sort by field (e.g. name, added_on, size, progress, dlspeed, upspeed, ratio)
        reverse: Reverse sort order
        search: Filter by torrent name
    """
    params = {}
    if filter:
        params["filter"] = filter
    if category:
        params["category"] = category
    if sort:
        params["sort"] = sort
    if reverse is not None:
        params["reverse"] = str(reverse).lower()
    if search:
        params["search"] = search

    resp = await _api("GET", "torrents/info", params=params)
    torrents = resp.json()
    # Compact output with hash and save_path
    lines = [f"Found {len(torrents)} torrent(s):\n"]
    for t in torrents:
        pct = t["progress"] * 100
        size_gb = t["size"] / (1024**3)
        speed = t.get("dlspeed", 0) / 1024
        eta = t.get("eta", -1)
        eta_str = (
            f"{eta // 3600}h{eta % 3600 // 60}m"
            if eta > 0 and eta != 8640000
            else "∞"
        )
        lines.append(
            f"  {t['name'][:60]:60s} | {t['state']:15s} | {pct:5.1f}% | {size_gb:5.2f}GB | {speed:7.0f}KB/s | ETA {eta_str}"
        )
        lines.append(
            f"    hash: {t['hash']} | save_path: {t.get('save_path', 'N/A')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def qbt_add_torrent(
    urls: Optional[str] = None,
    torrent_files: Optional[str] = None,
    savepath: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    paused: Optional[bool] = None,
    skip_checking: Optional[bool] = None,
) -> str:
    """Add one or more torrents to qBittorrent.

    Args:
        urls: Magnet or HTTP URLs, separated by newlines
        torrent_files: Local file paths to .torrent files, separated by newlines
        savepath: Download save path (overrides default)
        category: Category to assign
        tags: Comma-separated tags
        paused: Add in paused state
        skip_checking: Skip hash checking
    """
    data = {}
    if savepath:
        data["savepath"] = savepath
    if category:
        data["category"] = category
    if tags:
        data["tags"] = tags
    if paused is not None:
        data["paused"] = str(paused).lower()
    if skip_checking is not None:
        data["skip_checking"] = str(skip_checking).lower()
    if urls:
        data["urls"] = urls

    files = None
    if torrent_files:
        file_list = []
        for path in torrent_files.strip().split("\n"):
            path = path.strip()
            if path and os.path.isfile(path):
                file_list.append(
                    ("torrents", (os.path.basename(path), open(path, "rb")))
                )
        if file_list:
            files = file_list

    resp = await _api("POST", "torrents/add", data=data, files=files)
    # Close file handles
    if files:
        for _, (_, f) in files:
            f.close()
    return f"Added: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_pause_torrents(hashes: str) -> str:
    """Pause one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated (use 'all' for all torrents)
    """
    resp = await _api("POST", "torrents/pause", data={"hashes": hashes})
    return f"Paused: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_resume_torrents(hashes: str) -> str:
    """Resume one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated (use 'all' for all torrents)
    """
    resp = await _api("POST", "torrents/resume", data={"hashes": hashes})
    return f"Resumed: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_delete_torrents(hashes: str, delete_files: bool = False) -> str:
    """Delete one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated (use 'all' for all torrents)
        delete_files: Also delete downloaded files
    """
    resp = await _api(
        "POST",
        "torrents/delete",
        data={"hashes": hashes, "deleteFiles": str(delete_files).lower()},
    )
    return f"Deleted: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_torrent_info(hash: str) -> str:
    """Get detailed info for a specific torrent.

    Args:
        hash: Torrent hash
    """
    resp = await _api("GET", "torrents/properties", params={"hash": hash})
    info = resp.json()
    lines = []
    for k, v in info.items():
        if k in ("save_path", "name", "hash", "state", "size", "progress",
                 "dlspeed", "upspeed", "eta", "ratio", "nb_connections",
                 "seeds", "num_seeds", "leechers", "num_leechers",
                 "added_on", "completion_date", "last_seen", "total_uploaded",
                 "total_downloaded", "downloaded", "uploaded", "comment",
                 "category", "tags"):
            if k in ("size", "total_uploaded", "total_downloaded", "downloaded", "uploaded"):
                v = f"{v / (1024**3):.2f} GB"
            elif k in ("dlspeed", "upspeed"):
                v = f"{v / 1024:.0f} KB/s"
            elif k == "progress":
                v = f"{v * 100:.1f}%"
            elif k in ("added_on", "completion_date", "last_seen"):
                import datetime
                v = datetime.datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M") if v > 0 else "N/A"
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


@mcp.tool()
async def qbt_torrent_files(hash: str) -> str:
    """List files within a torrent.

    Args:
        hash: Torrent hash
    """
    resp = await _api("GET", "torrents/files", params={"hash": hash})
    files = resp.json()
    lines = [f"{len(files)} file(s):"]
    for f in files:
        size_gb = f["size"] / (1024**3)
        pct = f["progress"] * 100
        priority = {0: "skip", 1: "normal", 6: "high", 7: "max"}.get(
            f.get("priority", 1), str(f.get("priority", "?"))
        )
        lines.append(
            f"  {f['name'][:70]:70s} | {size_gb:5.2f}GB | {pct:5.1f}% | {priority}"
        )
    return "\n".join(lines)


@mcp.tool()
async def qbt_torrent_trackers(hash: str) -> str:
    """List trackers for a torrent.

    Args:
        hash: Torrent hash
    """
    resp = await _api("GET", "torrents/trackers", params={"hash": hash})
    trackers = resp.json()
    lines = []
    for t in trackers:
        if t.get("url", "").startswith("**"):
            continue  # Skip DHT/PeX/LPD
        url = t.get("url", "?")[:60]
        status = t.get("status", "?")
        seeds = t.get("num_seeds", 0)
        leechers = t.get("num_leechers", 0)
        msg = t.get("msg", "")[:40]
        lines.append(f"  {url:60s} | seeds:{seeds} leechers:{leechers} | {msg}")
    return "\n".join(lines) if lines else "No trackers found"


@mcp.tool()
async def qbt_add_trackers(hashes: str, urls: str) -> str:
    """Add trackers to one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated
        urls: Tracker URLs, one per line
    """
    resp = await _api(
        "POST", "torrents/addTrackers", data={"hashes": hashes, "urls": urls}
    )
    return f"Trackers added: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_set_category(hashes: str, category: str) -> str:
    """Set category for one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated
        category: Category name (must exist already)
    """
    resp = await _api(
        "POST", "torrents/setCategory", data={"hashes": hashes, "category": category}
    )
    return f"Category set: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_set_save_path(hashes: str, path: str) -> str:
    """Set save path for one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated
        path: New save path
    """
    resp = await _api(
        "POST", "torrents/setLocation", data={"hashes": hashes, "location": path}
    )
    return f"Save path set: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_recheck_torrents(hashes: str) -> str:
    """Recheck one or more torrents.

    Args:
        hashes: Torrent hash(es), pipe-separated
    """
    resp = await _api("POST", "torrents/recheck", data={"hashes": hashes})
    return f"Recheck started: {resp.text.strip() or 'OK'}"


@mcp.tool()
async def qbt_global_stats() -> str:
    """Get qBittorrent global transfer stats."""
    resp = await _api("GET", "transfer/info")
    info = resp.json()
    dl = info.get("dl_info_speed", 0) / (1024**2)
    ul = info.get("up_info_speed", 0) / (1024**2)
    dl_total = info.get("dl_info_data", 0) / (1024**3)
    ul_total = info.get("up_info_data", 0) / (1024**3)
    return (
        f"Download: {dl:.1f} MB/s | Upload: {ul:.1f} MB/s\n"
        f"Downloaded: {dl_total:.1f} GB | Uploaded: {ul_total:.1f} GB\n"
        f"Connection status: {info.get('connection_status', '?')}"
    )


@mcp.tool()
async def qbt_app_version() -> str:
    """Get qBittorrent application version and API version."""
    resp_v = await _api("GET", "app/version")
    resp_a = await _api("GET", "app/webapiVersion")
    return f"qBittorrent: {resp_v.text.strip()} | API: {resp_a.text.strip()}"


if __name__ == "__main__":
    _check_config()
    mcp.run()
