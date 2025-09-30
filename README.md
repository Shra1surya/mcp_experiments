# MCP Server Demo: Web Search + Google Sheets

This is a **Model Context Protocol (MCP) server** written in Python that exposes two tools:

- **`web_search`** → search the web using [Tavily](https://tavily.com) API  
- **`append_to_sheet`** → append rows into a Google Sheet using a service account

It’s a small but complete example of an **agentic AI workflow**:  
*Find information → Take an action with it.*

---

##  Features

- Built with the official [FastMCP Python SDK](https://modelcontextprotocol.io).  
- `web_search` uses Tavily’s API (free tier includes 1,000+ queries/month).  
- `append_to_sheet` calls Google Sheets REST API with OAuth service account credentials.  
- Tested with [MCP Inspector](https://github.com/modelcontextprotocol/inspector) for tool discovery and debugging.  
- Proxy/VPN safe: `requests` + service account token for Sheets, `httpx` for Tavily.  
- Minimal, single-file server (`server.py`) that you can extend with more tools.

---

## Requirements

- Ubuntu 24.04 (or any Linux / macOS; Windows WSL works too)  
- Python 3.10+  
- Node.js v22+ (via [nvm](https://github.com/nvm-sh/nvm)) for running Inspector  
- A [Tavily](https://tavily.com) API key  
- A Google Cloud project with the **Sheets API enabled** and a **service account JSON** key  
- The target Google Sheet shared with your service account email (Editor rights)

---

## Setup

### 1. Clone and venv
```bash
git clone https://github.com/<yourname>/mcp-websearch-sheets.git
cd mcp-websearch-sheets
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install deps
```bash
pip install --upgrade pip
pip install "mcp[cli]" httpx requests google-api-python-client google-auth google-auth-httplib2
```

### 3. Export env vars
```bash
export TAVILY_API_KEY="tvly_xxx"
export GOOGLE_APPLICATION_CREDENTIALS="/abs/path/to/service_account.json"

# optional: proxy
# export http_proxy="http://user:pass@proxy:port"
# export https_proxy="http://user:pass@proxy:port"
# export NO_PROXY="localhost,127.0.0.1"
```

### 4. Running the server
```bash
source .venv/bin/activate
python server.py
```

This starts an MCP server on **STDIO**. It doesn’t print results directly (all logs go to `stderr`).

---

## 🧪 Testing with MCP Inspector

1. Start Inspector (requires Node 22+):
   ```bash
   npx @modelcontextprotocol/inspector
   ```
   → open the URL shown in logs (http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=...).

2. Add your server:
   - Transport: **STDIO**
   - Command: `/abs/path/to/.venv/bin/python`
   - Args: `/abs/path/to/server.py`
   - Env: `TAVILY_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`

3. Invoke tools:
   - **web_search**
     ```json
     {
       "query": "world population",
       "search_depth": "basic",
       "max_results": 3
     }
     ```
   - **append_to_sheet**
     ```json
     {
       "spreadsheet_id": "<YOUR_SHEET_ID>",
       "range_name": "Sheet1!A2:C",
       "rows": [["Ping","https://example.com","hello"]]
     }
     ```

   Check your Google Sheet for the new row!

---

## Code Overview

### `web_search`
- Sends POST to `https://api.tavily.com/search`
- Header: `Authorization: Bearer <TAVILY_API_KEY>`
- Returns simplified results: title, URL, snippet.

### `append_to_sheet`
- Reads service account JSON from `GOOGLE_APPLICATION_CREDENTIALS`
- Uses `google-auth` to mint a short-lived Bearer token
- Calls:
  ```
  POST https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}:append
  ?valueInputOption=RAW&insertDataOption=INSERT_ROWS
  ```
- Sends rows in body; returns count of updated rows.

### Why this design?
- MCP’s `@tool` decorator makes both functions visible to Inspector (and any MCP client, including ChatGPT).  
- STDIO transport means it runs as a subprocess, clean and portable.  
- `httpx` and `requests` both respect `http_proxy`/`https_proxy`.  
- We avoided `httplib2` quirks by going direct REST for Sheets.

---

## Example Workflow

1. Run `web_search("AI chip shortage")`.  
2. Copy top 3 results.  
3. Run `append_to_sheet(spreadsheet_id="...", range_name="Sheet1!A2:C", rows=results)`.  
4. See your Google Sheet fill with live search results.

This demonstrates a mini agentic loop: **search → persist results**.

---

## Troubleshooting

- **Timeouts on Sheets**: check proxy/VPN. Disable VPN or whitelist `*.googleapis.com`.  
- **403 on Sheets**: make sure the target sheet is shared with your service account email.  
- **ModuleNotFoundError**: ensure pip install was done inside venv.  
- **Inspector won’t start**: check Node 22+ (`nvm install 22`).

---

## Next Steps

- Add more tools (e.g., summarize search results, export CSV).  
- Chain tools automatically with a small orchestrator script.  
- Deploy as a GitHub demo for Upwork / portfolio.

---

## License

MIT — use, learn, extend freely.

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io)  
- [Tavily Search API](https://tavily.com)  
- [Google Sheets API](https://developers.google.com/sheets/api)
