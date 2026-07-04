# ============================================================
# 1단계: React 프론트엔드 빌드 (Node)
# ============================================================
FROM node:22-alpine AS frontend
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================
# 2단계: Python 백엔드 (uv) + 빌드된 프론트엔드
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 의존성만 먼저 설치 (코드 변경 시 캐시 재사용)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 애플리케이션 코드
COPY mcp_server.py chat_agent.py google_auth.py start.sh ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

ENV PATH="/app/.venv/bin:$PATH"

# Railway가 PORT 환경 변수를 주입한다 (로컬 기본값 8001)
CMD ["bash", "start.sh"]
