.PHONY: build-app run-app run-mistral run-whisper run-db deploy update-app clean help

APP_IMAGE ?= studybuzz-app
APP_CONTAINER ?= studybuzz-app
APP_PORT ?= 5000

MISTRAL_CONTAINER ?= studybuzz-mistral
WHISPER_CONTAINER ?= studybuzz-whisper
DB_CONTAINER ?= pgvector_local
HUGGINGFACE_CACHE_PATH ?= $(HOME)/huggingface
HF_TOKEN ?=
NUM_GPUS ?= 8

help:
	@echo "StudyBuzz Podman Deployment"
	@echo ""
	@echo "Targets:"
	@echo "  make build-app     - Build the StudyBuzz Docker image"
	@echo "  make run-app       - Build and run the StudyBuzz container"
	@echo "  make run-mistral   - Run the Mistral vLLM container"
	@echo "  make run-whisper   - Run the Whisper vLLM container"
	@echo "  make run-db        - Run the PostgreSQL/pgvector database container"
	@echo "  make deploy        - Create pod and start all containers"
	@echo "  make update-app    - Fast restart of JUST the Flask application container"
	@echo "  make clean         - Stop and remove all containers"

build-app:
	@echo "Building StudyBuzz image..."
	podman build -t $(APP_IMAGE) .

run-app: build-app
	@echo "Starting StudyBuzz container..."
	@mkdir -p uploads output/video
	podman run -d \
	  -p $(APP_PORT):5000 \
	  -e VIP_DB_HOST=host.containers.internal \
	  -v $(PWD)/uploads:/app/uploads:Z \
	  -v $(PWD)/output:/app/output:Z \
	  --name $(APP_CONTAINER) \
	  $(APP_IMAGE)
	@echo "StudyBuzz started on port $(APP_PORT)"

run-mistral:
	@echo "Starting Mistral vLLM container..."
	@mkdir -p output/video
	podman run -d \
	  --device nvidia.com/gpu=all \
	  --security-opt=label=disable \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  -v $(PWD)/output/video:/root/video \
	  -p 8000:8000 \
	  --env "HUGGING_FACE_HUB_TOKEN=$(HF_TOKEN)" \
	  --env "NCCL_DEBUG=INFO" \
	  --env "OMP_NUM_THREADS=16" \
	  --name $(MISTRAL_CONTAINER) \
	  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
	  --model mistralai/Mistral-Large-3-675B-Instruct-2512 \
	  --served-model-name mistral-large \
	  --tensor-parallel-size $(NUM_GPUS) \
	  --gpu-memory-utilization 0.90 \
	  --max-model-len 196608 \
	  --limit-mm-per-prompt '{"image": 32}' \
	  --max-num-batched-tokens 8192 \
	  --enable-chunked-prefill \
	  --max-num-seqs 2 \
	  --load-format mistral \
	  --tokenizer-mode mistral \
	  --config-format mistral \
	  --enable-auto-tool-choice \
	  --tool-call-parser mistral \
	  --allowed-local-media-path /root/video \
	  --host 0.0.0.0 \
	  --port 8000
	@echo "Mistral vLLM started on port 8000 (model loading takes ~20 min)"

run-whisper:
	@echo "Starting Whisper vLLM container..."
	podman run -d \
	  --restart unless-stopped \
	  --device nvidia.com/gpu=all \
	  --security-opt=label=disable \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  -p 8001:8000 \
	  --env "HUGGING_FACE_HUB_TOKEN=$(HF_TOKEN)" \
	  --env "VLLM_USE_DEEP_GEMM=0" \
	  --entrypoint /bin/bash \
	  --name $(WHISPER_CONTAINER) \
	  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
	  -c "pip install librosa soundfile && python3 -m vllm.entrypoints.openai.api_server \
	    --model openai/whisper-large-v3 \
	    --served-model-name whisper \
	    --dtype bfloat16 \
	    --max-model-len 448 \
	    --tensor-parallel-size 1 \
	    --swap-space 16 \
	    --gpu-memory-utilization 0.075 \
	    --trust-remote-code \
	    --host 0.0.0.0 \
	    --port 8000"
	@echo "Whisper vLLM started on port 8001 (model loading takes ~2 min)"

run-db:
	@echo "Starting PostgreSQL pgvector database container..."
	@mkdir -p $(PWD)/my_pgdata
	@podman ps -a --filter "name=^$(DB_CONTAINER)$$" --format "{{.Names}}" | grep -q $(DB_CONTAINER) && podman rm -f $(DB_CONTAINER) || true
	podman run -d \
	  --name $(DB_CONTAINER) \
	  --userns=keep-id \
	  --net=host \
	  -e POSTGRES_PASSWORD=mysecret \
	  -e PGDATA=/var/lib/postgresql/data/pgdata \
	  -e PGPORT=5432 \
	  -v $(PWD)/my_pgdata:/var/lib/postgresql/data:Z \
	  pgvector/pgvector:pg18-trixie
	@echo "PostgreSQL pgvector database started on port 5432"

deploy: build-app run-db
	@echo "Creating pod for shared networking..."
	@podman pod exists studybuzz-pod || podman pod create --name studybuzz-pod -p $(APP_PORT):5000 -p 8000:8000 -p 8001:8001
	@echo "Starting Mistral vLLM in pod..."
	@mkdir -p output/video uploads
	@podman ps -a --filter "name=^$(MISTRAL_CONTAINER)$$" --format "{{.Names}}" | grep -q $(MISTRAL_CONTAINER) && podman rm -f $(MISTRAL_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(MISTRAL_CONTAINER) \
	  --device nvidia.com/gpu=all \
	  --security-opt=label=disable \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  -v $(PWD)/output/video:/root/video \
	  --env "HUGGING_FACE_HUB_TOKEN=$(HF_TOKEN)" \
	  --env "NCCL_DEBUG=INFO" \
	  --env "OMP_NUM_THREADS=16" \
	  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
	  --model mistralai/Mistral-Large-3-675B-Instruct-2512 \
	  --served-model-name mistral-large \
	  --tensor-parallel-size $(NUM_GPUS) \
	  --gpu-memory-utilization 0.90 \
	  --max-model-len 196608 \
	  --limit-mm-per-prompt '{"image": 32}' \
	  --max-num-batched-tokens 8192 \
	  --enable-chunked-prefill \
	  --max-num-seqs 2 \
	  --load-format mistral \
	  --tokenizer-mode mistral \
	  --config-format mistral \
	  --enable-auto-tool-choice \
	  --tool-call-parser mistral \
	  --allowed-local-media-path /root/video \
	  --host 0.0.0.0 \
	  --port 8000
	@echo "Starting Whisper vLLM in pod..."
	@podman ps -a --filter "name=^$(WHISPER_CONTAINER)$$" --format "{{.Names}}" | grep -q $(WHISPER_CONTAINER) && podman rm -f $(WHISPER_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(WHISPER_CONTAINER) \
	  --restart unless-stopped \
	  --device nvidia.com/gpu=all \
	  --security-opt=label=disable \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  --env "HUGGING_FACE_HUB_TOKEN=$(HF_TOKEN)" \
	  --env "VLLM_USE_DEEP_GEMM=0" \
	  --entrypoint /bin/bash \
	  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
	  -c "pip install librosa soundfile && python3 -m vllm.entrypoints.openai.api_server \
	    --model openai/whisper-large-v3 \
	    --served-model-name whisper \
	    --dtype bfloat16 \
	    --max-model-len 448 \
	    --tensor-parallel-size 1 \
	    --swap-space 16 \
	    --gpu-memory-utilization 0.075 \
	    --trust-remote-code \
	    --host 0.0.0.0 \
	    --port 8001"
	@echo "Starting StudyBuzz app container..."
	@podman ps -a --filter "name=^$(APP_CONTAINER)$$" --format "{{.Names}}" | grep -q $(APP_CONTAINER) && podman rm -f $(APP_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(APP_CONTAINER) \
	  -e VIP_DB_HOST=host.containers.internal \
	  -v $(PWD)/uploads:/app/uploads:Z \
	  -v $(PWD)/output:/app/output:Z \
	  $(APP_IMAGE)
	@echo ""
	@echo "Deployment complete!"
	@echo "StudyBuzz:  http://localhost:$(APP_PORT)"
	@echo "Mistral:   http://localhost:8000"
	@echo "Whisper:   http://localhost:8001"

update-whisper:
	@echo "Updating Whisper container..."
	@podman ps -a --filter "name=^$(WHISPER_CONTAINER)$$" --format "{{.Names}}" | grep -q $(WHISPER_CONTAINER) && podman rm -f $(WHISPER_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(WHISPER_CONTAINER) \
	  --restart unless-stopped \
	  --device nvidia.com/gpu=all \
	  --security-opt=label=disable \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  --env "HUGGING_FACE_HUB_TOKEN=$(HF_TOKEN)" \
	  --env "VLLM_USE_DEEP_GEMM=0" \
	  --entrypoint /bin/bash \
	  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
	  -c "pip install librosa soundfile && python3 -m vllm.entrypoints.openai.api_server \
	    --model openai/whisper-large-v3 \
	    --served-model-name whisper \
	    --dtype bfloat16 \
	    --max-model-len 448 \
	    --tensor-parallel-size 1 \
	    --swap-space 16 \
	    --gpu-memory-utilization 0.075 \
	    --trust-remote-code \
	    --host 0.0.0.0 \
	    --port 8001"
	@echo "Whisper update complete! Re-loading the model..."

update-app: build-app
	@echo "Updating StudyBuzz app container..."
	@podman ps -a --filter "name=^$(APP_CONTAINER)$$" --format "{{.Names}}" | grep -q $(APP_CONTAINER) && podman rm -f $(APP_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(APP_CONTAINER) \
	  -e VIP_DB_HOST=host.containers.internal \
	  -v $(PWD)/uploads:/app/uploads:Z \
	  -v $(PWD)/output:/app/output:Z \
	  $(APP_IMAGE)
	@echo ""
	@echo "App Update Complete! Fast refresh finished."

clean:
	@echo "Removing containers..."
	-podman rm -f $(APP_CONTAINER)
	-podman rm -f $(MISTRAL_CONTAINER)
	-podman rm -f $(WHISPER_CONTAINER)
	-podman rm -f $(DB_CONTAINER)
	-podman pod rm -f studybuzz-pod 2>/dev/null || true
	@echo "All containers and pod removed"
