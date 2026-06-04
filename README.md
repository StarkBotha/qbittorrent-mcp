# qBittorrent MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that exposes the
[qBittorrent WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1%2B))
to LLMs. Lets an AI assistant list, add, pause, resume, delete, and inspect torrents on a
remote qBittorrent instance — including save-path changes (which auto-move files on disk)
and tracker management.

## Tools

| Tool | Purpose |
|------|---------|
| `qbt_list_torrents` | List torrents with filter / category / sort / search. Returns hash + save_path per row. |
| `qbt_add_torrent` | Add magnet / HTTP URLs or local `.torrent` files. Optional save path, category, tags. |
| `qbt_pause_torrents` | Pause one or more torrents (or all). |
| `qbt_resume_torrents` | Resume one or more torrents (or all). |
| `qbt_delete_torrents` | Delete torrents, optionally with downloaded files. |
| `qbt_torrent_info` | Detailed properties for a single torrent (size, speeds, ratio, dates, etc.). |
| `qbt_torrent_files` | List files inside a torrent with size / progress / priority. |
| `qbt_torrent_trackers` | List trackers (skips DHT / PeX / LPD pseudo-trackers). |
| `qbt_add_trackers` | Append trackers to existing torrents. |
| `qbt_set_category` | Assign a category (must already exist in qBittorrent). |
| `qbt_set_save_path` | Move one or more torrents to a new path (auto-moves files). |
| `qbt_recheck_torrents` | Force recheck / re-verify torrent data. |
| `qbt_global_stats` | Global up / down speeds and lifetime totals. |
| `qbt_app_version` | qBittorrent version + WebAPI version. |

## Requirements

- Python 3.10+
- A running qBittorrent instance with the WebUI enabled (default port 8080)
- `pip` packages: `mcp` and `httpx`

## Installation

```bash
git clone https://github.com/StarkBotha/qbittorrent-mcp.git
cd qbittorrent-mcp
pip install -r requirements.txt
```

## Configuration

All configuration is via environment variables — no defaults that leak credentials.

| Variable | Required | Description |
|----------|----------|-------------|
| `QBT_URL`  | **yes** | Base URL of qBittorrent WebUI, e.g. `http://localhost:8080` or `https://qbittorrent.example.com` |
| `QBT_USER` | no | WebUI username (defaults to `admin`) |
| `QBT_PASS` | **yes** | WebUI password |

The server re-authenticates automatically if the session cookie expires (HTTP 403).

> **HTTPS note:** the HTTP client disables certificate verification by default. This is
> convenient for self-signed certs behind reverse proxies (Caddy, nginx, Cloudflare Tunnel,
> `*.loclx.io`, etc.) but is unsafe on the open internet. Tunnel or VPN the connection
> rather than exposing qBittorrent directly.

## Run

```bash
export QBT_URL=http://localhost:8080
export QBT_USER=admin
export QBT_PASS=yourpassword
python server.py
```

### Claude Desktop / Hermes / other MCP clients

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "qbittorrent": {
      "command": "python",
      "args": ["/path/to/qbittorrent-mcp/server.py"],
      "env": {
        "QBT_URL":  "http://localhost:8080",
        "QBT_USER": "admin",
        "QBT_PASS": "yourpassword"
      }
    }
  }
}
```

## License

MIT — see [LICENSE](LICENSE).
