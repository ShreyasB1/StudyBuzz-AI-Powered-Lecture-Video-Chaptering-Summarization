# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/video-summarizer-ui/package.json frontend/video-summarizer-ui/package-lock.json ./
RUN npm ci

COPY frontend/video-summarizer-ui/ ./
RUN npm run build

# Stage 2: Python runtime with Flask, FFmpeg, and OpenCV
FROM python:3.11

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_backend.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements_backend.txt

COPY app.py timeStampGen.py ./

COPY --from=frontend-builder /app/frontend/build frontend/video-summarizer-ui/build

RUN mkdir -p uploads output/video

EXPOSE 5000

CMD ["python", "app.py"]
