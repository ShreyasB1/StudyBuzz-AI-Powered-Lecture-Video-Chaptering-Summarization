FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

RUN mkdir -p uploads output/video

EXPOSE 5000

CMD ["sh", "-c", "python init_db.py && python app.py"]
