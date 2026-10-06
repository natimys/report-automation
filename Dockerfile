FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DATA_DIR=/app/data
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/templates ./templates
COPY --from=frontend-build /frontend/dist ./frontend/dist
RUN mkdir -p /app/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/reports', timeout=3)" || exit 1
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
