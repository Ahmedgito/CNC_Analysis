FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    LOG_FORMAT=json

WORKDIR /app

# The OpenCascade wheel (cadquery-ocp-novtk) links the GL and X runtime libraries even though
# the app never renders on the server; without them `import OCP` fails.
RUN apt-get update  && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxrender1 libxext6 libfontconfig1  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
