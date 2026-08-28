# Read-only Repair Agent (Starlette/uvicorn, :8010)
# Env (OpenRouter key, GitHub MCP PATs, shared token) is provided at runtime
# via compose env_file — NOT baked into the image (see .dockerignore).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8010

# Settings.from_environment() runs in create_app, so all required vars must be
# in the process env at startup (compose env_file supplies them).
CMD ["uvicorn", "--factory", "repair_agent.api:create_app", "--host", "0.0.0.0", "--port", "8010"]
