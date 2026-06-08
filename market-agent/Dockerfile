# Backend container: FastAPI + Google ADK agent + Phoenix MCP (needs Node for npx).
FROM python:3.12-slim

# Node.js 20 (for the Phoenix MCP server via npx) + uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir uv==0.8.13

# Pre-cache the Phoenix MCP server so the first /insights call doesn't download it.
RUN npm install -g @arizeai/phoenix-mcp@latest

WORKDIR /code

COPY ./pyproject.toml ./README.md ./uv.lock ./
COPY ./app ./app
COPY ./server.py ./

RUN uv sync --frozen --no-dev

# Cloud Run provides $PORT (defaults to 8080).
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uv run uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
