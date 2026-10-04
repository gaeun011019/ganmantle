# Linux amd64/arm64에서 각자 빌드합니다. 모델은 이미지에 넣지 않습니다.
FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS backend-deps
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/models/fasttext-ko \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r backend/requirements.lock \
    && useradd --create-home --uid 10001 appuser

FROM node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34 AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM backend-deps
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY model-manifest.json /app/model-manifest.json
COPY --from=frontend /build/dist /app/frontend/dist
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
