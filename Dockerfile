# Stage 1: Build the React/Vite frontend
FROM docker.io/library/node:20-slim AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BUILD_FRONTEND=0

# APT::Sandbox::User=root avoids privilege-drop failures under
# rootless Podman without subuid ranges (common on shared HPC clusters).
RUN apt-get -o APT::Sandbox::User=root update && \
    apt-get -o APT::Sandbox::User=root install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_backend.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements_backend.txt

COPY app.py timeStampGen.py vllm_to_vtt.py init_db.py ./
COPY static/ static/
COPY --from=frontend-builder /build/dist/ frontend/dist/

RUN mkdir -p uploads output/video

EXPOSE 5000

CMD ["sh", "-c", "python init_db.py && python app.py"]
