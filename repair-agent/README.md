# Read-Only Repair Agent

Phase 1 investigates eligible application defects with a fixed OpenRouter
model and the official remote GitHub MCP endpoint. It returns bounded proposed
changes and never writes to GitHub.

## Configuration

Copy the variable names from `.env.example` into the process environment.
Use a read-only fine-grained GitHub PAT and one fixed OpenRouter model that
supports tool calling and structured output. The backend and repair agent must
share the same `REPAIR_AGENT_SHARED_TOKEN`.

## Run

```powershell
./.venv/Scripts/python.exe -m uvicorn --factory repair_agent.api:create_app --env-file .env --host 127.0.0.1 --port 8010
```

Normal tests use fake MCP and provider implementations:

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The remote MCP connectivity probe is opt-in:

```powershell
$env:RUN_LIVE_GITHUB_MCP_TEST = "1"
./.venv/Scripts/python.exe ./test_github_mcp.py
```

Legacy Ollama, Serena, local MCP, and cloned-workspace experiments are retained
under `legacy/` and are not imported by the active runtime.
