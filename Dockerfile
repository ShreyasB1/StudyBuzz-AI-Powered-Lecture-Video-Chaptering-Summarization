FROM docker.io/library/node:20-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BUILD_FRONTEND=0

# node:20-slim (Debian bookworm) is the only base image that works on PACE's
# rootless Podman (single UID mapping, no subuid/subgid ranges).
# python:3.11-slim and alpine images both fail with crun /bin/sh errors.

# Install Python + download helpers.
# FFmpeg is NOT installed via apt — its fontconfig dependency chain runs
# chown in post-install scripts, which errors under single UID mapping.
RUN apt-get -o APT::Sandbox::User=root update && \
    apt-get -o APT::Sandbox::User=root install -y --no-install-recommends \
    python3 python3-pip python3-dev ca-certificates wget xz-utils \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Static FFmpeg binary — fully self-contained, zero system library deps.
# Source: BtbN/FFmpeg-Builds on GitHub (rebuilt daily, stable URL).
RUN wget -q "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" \
      -O /tmp/ffmpeg.tar.xz && \
    mkdir -p /tmp/ffmpeg && \
    tar -xf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg --strip-components=1 --no-same-owner && \
    cp /tmp/ffmpeg/bin/ffmpeg /usr/local/bin/ && \
    cp /tmp/ffmpeg/bin/ffprobe /usr/local/bin/ && \
    rm -rf /tmp/ffmpeg /tmp/ffmpeg.tar.xz && \
    ffmpeg -version

# Build React frontend
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm install

COPY frontend/ frontend/
RUN cd frontend && npm run build && \
    mv dist /app/frontend_dist && \
    rm -rf /app/frontend && \
    mkdir -p /app/frontend && \
    mv /app/frontend_dist /app/frontend/dist

# Install Python dependencies
COPY requirements.txt requirements_backend.txt ./
RUN pip install --break-system-packages --upgrade pip && \
    pip install --break-system-packages -r requirements.txt && \
    pip install --break-system-packages -r requirements_backend.txt

COPY app.py timeStampGen.py vllm_to_vtt.py init_db.py ./
COPY static/ static/

RUN mkdir -p uploads output/video

EXPOSE 5000

CMD ["sh", "-c", "python init_db.py && python app.py"]
