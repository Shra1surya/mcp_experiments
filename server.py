#!/usr/bin/env python3
"""
MCP server exposing two tools:
  1) web_search        -> Tavily Search API (Bearer key)
  2) append_to_sheet   -> Google Sheets API (service account)

Env vars expected:
  TAVILY_API_KEY=tvly_...                         (required for web_search)
  GOOGLE_APPLICATION_CREDENTIALS=/abs/path/sa.json
    - or SERVICE_ACCOUNT_FILE=/abs/path/sa.json   (one of these is required)

Optional proxy env (both cases supported):
  http_proxy / https_proxy   and/or   HTTP_PROXY / HTTPS_PROXY
  NO_PROXY="localhost,127.0.0.1"

Notes:
- Uses FastMCP (STDIO). Do NOT print to stdout; logs go to stderr.
- httpx auto-honors proxy envs; Google client is wired with AuthorizedHttp + ProxyInfo.
"""

import os
import sys
import json
import logging
import urllib.parse
from typing import Any, Dict, List, Literal, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Google Sheets client pieces
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google_auth_httplib2 import AuthorizedHttp
import httplib2
try:
    from httplib2 import socks
    PROXY_TYPE_HTTP = getattr(socks, "PROXY_TYPE_HTTP", 3)
except Exception:
    socks = None
    PROXY_TYPE_HTTP = 3

# --------------------------- logging (stderr) ---------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("mcp-websearch-sheets")

# --------------------------- MCP server --------------------------------------
# Bump request window so slow networks/proxies don't trip client timeouts
mcp = FastMCP("WebSearchAndSheets")

# =============================================================================
# Web search tool (Tavily)
# =============================================================================

TAVILY_ENDPOINT = "https://api.tavily.com/search"
TAVILY_KEY = os.environ.get("TAVILY_API_KEY")

@mcp.tool()
def web_search(
    query: str,
    search_depth: Literal["basic", "advanced"] = "basic",
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Perform a web search via Tavily and return structured results.
    Returns: {"query": str, "results": [{"title","url","content"}...]}
    """
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY is not set")

    if not query or not isinstance(query, str):
        raise ValueError("query must be a non-empty string")

    payload = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 20)),
    }

    headers = {
        "Authorization": f"Bearer {TAVILY_KEY}",
        "Content-Type": "application/json",
    }

    log.info("Tavily request: %s", payload)

    # httpx respects proxy env vars automatically
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(TAVILY_ENDPOINT, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    out: List[Dict[str, str]] = []
    for item in data.get("results", [])[: payload["max_results"]]:
        out.append(
            {
                "title": (item.get("title") or "")[:300],
                "url": item.get("url") or "",
                "content": (item.get("content") or "")[:2000],  # trim to keep payloads lean
            }
        )

    return {"query": query, "results": out}

# =============================================================================
# Google Sheets tool (append rows)
# =============================================================================

_sheets_service = None  # lazy init

def _proxy_info_from_env() -> Optional[httplib2.ProxyInfo]:
    """
    Build ProxyInfo manually (works on all httplib2 versions).
    Supports http://user:pass@host:port and https://...
    """
    url = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    if not url:
        return None
    p = urllib.parse.urlparse(url)
    return httplib2.ProxyInfo(
        proxy_type=PROXY_TYPE_HTTP,
        proxy_host=p.hostname,
        proxy_port=p.port or 8080,
        proxy_user=p.username,
        proxy_pass=p.password,
    )

def _init_sheets_service():
    global _sheets_service
    if _sheets_service is not None:
        return _sheets_service

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    key_path = os.environ.get("SERVICE_ACCOUNT_FILE") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path:
        raise RuntimeError("Set GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_FILE to your service account JSON")
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Credential file not found: {key_path}")

    creds = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)

    # Wire proxy + timeout explicitly for Google client
    pinfo = _proxy_info_from_env()
    http = httplib2.Http(timeout=30, proxy_info=pinfo)
    authed_http = AuthorizedHttp(creds, http=http)

    # IMPORTANT: pass only http=..., not credentials=...
    _sheets_service = build("sheets", "v4", http=authed_http, cache_discovery=False)
    return _sheets_service

@mcp.tool()
def append_to_sheet(
    spreadsheet_id: str,
    range_name: str,           # e.g. "Sheet1!A2:D"
    rows: List[List[str]],     # e.g. [["Title","URL","Snippet"], ...]
) -> Dict[str, Any]:
    """
    Appends rows to a Google Sheet using values.append.
    Returns: {"updatedRows": int}
    """
    if not spreadsheet_id:
        raise ValueError("spreadsheet_id is required")
    if not range_name:
        raise ValueError("range_name is required")
    if not isinstance(rows, list) or (rows and not isinstance(rows[0], list)):
        raise ValueError("rows must be a list of lists")

    service = _init_sheets_service()
    body = {"values": rows}

    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute(num_retries=2)
    )

    updated = int(result.get("updates", {}).get("updatedRows") or 0)
    log.info("Sheets append: spreadsheet=%s range=%s rows=%d", spreadsheet_id, range_name, updated)
    return {"updatedRows": updated}

# =============================================================================
# Main entry (STDIO)
# =============================================================================

def main():
    # Start the MCP server over stdio. Do NOT print to stdout.
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

