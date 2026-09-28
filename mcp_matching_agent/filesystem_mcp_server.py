"""Filesystem MCP server for the recruitment matching agent.

The official MCP SDK owns JSON-RPC 2.0 framing, lifecycle, discovery and transport.
This server exposes filesystem operations as MCP tools and resume/files as MCP resources.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:  # compatibility with MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "server_config.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("filesystem-mcp")


def load_config() -> dict[str, Any]:
    """Load JSON configuration, falling back to safe defaults."""
    defaults = {
        "resume_directory": str(ROOT / "data" / "resumes"),
        "allowed_extensions": [".txt", ".md", ".json"],
        "max_file_size_mb": 5,
        "watch_poll_seconds": 2,
        "server_name": "Recruitment Filesystem MCP",
    }
    try:
        with DEFAULT_CONFIG.open("r", encoding="utf-8") as fh:
            defaults.update(json.load(fh))
    except FileNotFoundError:
        pass
    return defaults


CONFIG = load_config()
RESUME_DIR = Path(CONFIG["resume_directory"]).expanduser().resolve()
ALLOWED = {str(x).lower() for x in CONFIG["allowed_extensions"]}
MAX_BYTES = int(float(CONFIG["max_file_size_mb"]) * 1024 * 1024)

mcp = MCPServer(str(CONFIG["server_name"]))


def _safe_path(path: str) -> Path:
    """Resolve a path and prevent access outside the configured resume directory."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = RESUME_DIR / candidate
    candidate = candidate.expanduser().resolve()
    try:
        candidate.relative_to(RESUME_DIR)
    except ValueError as exc:
        raise ValueError("Path is outside the configured resume directory") from exc
    return candidate


def _validate_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.name}")
    if not path.is_file():
        raise IsADirectoryError(f"Not a file: {path.name}")
    if path.suffix.lower() not in ALLOWED:
        raise ValueError(f"Unsupported extension: {path.suffix or '<none>'}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"File exceeds configured limit of {MAX_BYTES} bytes")


def _list_files() -> list[dict[str, Any]]:
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for p in sorted(RESUME_DIR.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in ALLOWED:
            result.append({
                "name": p.name,
                "path": str(p.relative_to(RESUME_DIR)),
                "size": p.stat().st_size,
                "modified": p.stat().st_mtime,
                "uri": f"resume://{p.name}",
            })
    return result


@mcp.resource("filesystem://index")
def filesystem_index() -> str:
    """Discover the configured resume filesystem and available files."""
    return json.dumps({
        "server": CONFIG["server_name"],
        "resume_directory": str(RESUME_DIR),
        "allowed_extensions": sorted(ALLOWED),
        "files": _list_files(),
    }, indent=2)


@mcp.resource("resume://{filename}")
def resume_resource(filename: str) -> str:
    """Read one resume as an MCP resource."""
    path = _safe_path(filename)
    _validate_file(path)
    return path.read_text(encoding="utf-8", errors="replace")


@mcp.resource("config://server")
def server_config_resource() -> str:
    """Expose non-secret server configuration for resource discovery."""
    public_config = dict(CONFIG)
    return json.dumps(public_config, indent=2)


@mcp.tool()
def list_files(extension: str = "") -> dict[str, Any]:
    """List resume files in the configured directory, optionally filtered by extension."""
    files = _list_files()
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        files = [f for f in files if f["name"].lower().endswith(ext.lower())]
    return {"count": len(files), "files": files}


@mcp.tool()
def read_file(filename: str) -> dict[str, Any]:
    """Read a resume file through the MCP server."""
    path = _safe_path(filename)
    _validate_file(path)
    return {"filename": path.name, "content": path.read_text(encoding="utf-8", errors="replace")}


@mcp.tool()
def search_files(query: str, extension: str = "") -> dict[str, Any]:
    """Search resume contents case-insensitively and return matching files/snippets."""
    if not query.strip():
        raise ValueError("query must not be empty")
    matches = []
    for item in _list_files():
        if extension and not item["name"].lower().endswith(extension.lower() if extension.startswith(".") else f".{extension.lower()}"):
            continue
        path = _safe_path(item["path"])
        text = path.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        if query.lower() in low:
            pos = low.index(query.lower())
            matches.append({"filename": item["name"], "snippet": text[max(0, pos-100):pos+300]})
    return {"query": query, "count": len(matches), "matches": matches}


@mcp.tool()
def write_file(filename: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Write a text file inside the configured resume directory."""
    path = _safe_path(filename)
    if path.suffix.lower() not in ALLOWED:
        raise ValueError(f"Unsupported extension: {path.suffix}")
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Content exceeds configured file-size limit")
    if path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path.name}; use overwrite=true")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"success": True, "filename": path.name, "bytes": path.stat().st_size}


@mcp.tool()
def watch_directory(seconds: int = 5) -> dict[str, Any]:
    """Poll for new/changed resume files and return changes observed in the interval."""
    seconds = max(1, min(int(seconds), 60))
    before = {f["name"]: f["modified"] for f in _list_files()}
    time.sleep(seconds)
    after = {f["name"]: f["modified"] for f in _list_files()}
    new_files = sorted([name for name in after if name not in before])
    changed_files = sorted([name for name in after if name in before and after[name] > before[name] + 1e-6])
    return {"watched_seconds": seconds, "new_files": new_files, "changed_files": changed_files}


@mcp.tool()
def batch_process(filenames: list[str] | None = None) -> dict[str, Any]:
    """Read multiple resume files in one MCP call and return structured documents."""
    names = filenames if filenames is not None else [f["name"] for f in _list_files()]
    documents, errors = [], []
    for filename in names:
        try:
            path = _safe_path(filename)
            _validate_file(path)
            documents.append({"filename": path.name, "content": path.read_text(encoding="utf-8", errors="replace")})
        except (OSError, ValueError) as exc:
            errors.append({"filename": filename, "error": str(exc)})
    return {"requested": len(names), "processed": len(documents), "documents": documents, "errors": errors}


@mcp.tool()
def server_status() -> dict[str, Any]:
    """Return server health and configuration status."""
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "status": "ok",
        "server": CONFIG["server_name"],
        "resume_directory_exists": RESUME_DIR.exists(),
        "file_count": len(_list_files()),
        "allowed_extensions": sorted(ALLOWED),
    }


if __name__ == "__main__":
    # SDK owns JSON-RPC 2.0 and stdio framing; stdout must remain protocol-only.
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
