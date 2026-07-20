# 백엔드 (FastAPI) — uv 멀티스테이지 빌드
# 빌드: docker build -t ica-backend -f Dockerfile .
# 실행 진입점은 uvicorn(단일 워커) — 수평 확장은 compose --scale backend=N 으로.

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# 일부 휠 컴파일 대비(최종 스테이지엔 미포함)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
# 의존성 레이어 캐시 — 소스 변경과 분리
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
# 애플리케이션 + alembic
COPY app ./app
COPY prompts ./prompts
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
# 런타임 시스템 라이브러리 (onnxruntime/chromadb 의 libgomp)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app /app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
