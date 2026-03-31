FROM docker.io/library/node:20-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BUILD_FRONTEND=0

# node:20-slim is Debian bookworm and works on PACE's rootless Podman.
# python:3.11-slim does NOT work (crun /bin/sh issue under single UID mapping).

# 1) Install Python (clean — no fontconfig deps)
RUN apt-get -o APT::Sandbox::User=root update && \
    apt-get -o APT::Sandbox::User=root install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# 2) Install FFmpeg separately with --force-all.
#    fontconfig's post-install script runs chown which fails under rootless
#    Podman's single UID mapping. The FFmpeg binary itself works fine for
#    audio/video processing — we don't need font rendering.
RUN apt-get -o APT::Sandbox::User=root update && \
    (apt-get -o APT::Sandbox::User=root \
      -o Dpkg::Options::="--force-all" \
      install -y --no-install-recommends ffmpeg || true) && \
    ffmpeg -version && \
    rm -rf /var/lib/apt/lists/*

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
