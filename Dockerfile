# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    A_STELLAR_STATIC_DIR=/app/frontend/dist \
    A_STELLAR_ROUTING_MODE=computed \
    A_STELLAR_DATASET_DIR=/datasets \
    A_STELLAR_PLANNING_PROFILE=/run/a-stellar/planning.json \
    A_STELLAR_ROUTE_STORE=/var/lib/a-stellar/routes \
    A_STELLAR_A0_USAGE_STORE=/var/lib/a-stellar/a0-usage
WORKDIR /app/backend
COPY backend/pyproject.toml backend/constraints-runtime.txt ./
COPY backend/app ./app
RUN python -m pip install --no-cache-dir --only-binary=numpy,rasterio,pyproj \
      -c constraints-runtime.txt '.[planning,agentic]' \
    && groupadd --gid 10001 stellar \
    && useradd --uid 10001 --gid stellar --no-create-home stellar \
    && mkdir -p /var/lib/a-stellar /run/a-stellar \
    && chmod 1777 /var/lib/a-stellar
COPY --from=frontend /build/frontend/dist /app/frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=4).close()"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
