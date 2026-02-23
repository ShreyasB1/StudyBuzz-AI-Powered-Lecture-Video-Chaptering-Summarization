.PHONY: build-app run-app run-vllm deploy clean help

APP_IMAGE ?= studybuzz-app
APP_CONTAINER ?= studybuzz-app
APP_PORT ?= 5000

VLLM_CONTAINER ?= studybuzz-vllm
VLLM_PORT ?= 8000
HUGGINGFACE_CACHE_PATH ?= $(HOME)/huggingface
WHISPER_PATH ?= $(HOME)/whisper
NUM_GPUS ?= 8

help:
	@echo "StudyBuzz Podman Deployment"
	@echo ""
	@echo "Targets:"
	@echo "  make build-app     - Build the StudyBuzz Docker image"
	@echo "  make run-app       - Build and run the StudyBuzz container"
	@echo "  make run-vllm      - Run the vLLM container"
	@echo "  make deploy        - Create pod and start all containers"
	@echo "  make clean         - Stop and remove all containers"

build-app:
	@echo "Building StudyBuzz image..."
	podman build -t $(APP_IMAGE) .

run-app: build-app
	@echo "Starting StudyBuzz container..."
	@mkdir -p uploads output/video
	podman run -d \
	  -p $(APP_PORT):5000 \
	  -v $(PWD)/uploads:/app/uploads:Z \
	  -v $(PWD)/output:/app/output:Z \
	  -v $(WHISPER_PATH):/opt/whisper:ro \
	  -e PATH="/opt/whisper:$$PATH" \
	  --name $(APP_CONTAINER) \
	  $(APP_IMAGE)
	@echo "StudyBuzz started on port $(APP_PORT)"

run-vllm:
	@echo "Starting vLLM container..."
	@mkdir -p output/video
	podman run -d \
	  --device nvidia.com/gpu=all \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  -v $(PWD)/output/video:/root/video \
	  -p $(VLLM_PORT):8000 \
	  --name $(VLLM_CONTAINER) \
	  docker.io/vllm/vllm-openai:latest \
	  --model Qwen/Qwen3-VL-235B-A22B-Thinking-FP8 \
	  --served-model-name Qwen3-VL \
	  --enable-expert-parallel \
	  --swap-space 16 \
	  --max-num-seqs 512 \
	  --gpu-memory-utilization 0.9 \
	  --tensor-parallel-size $(NUM_GPUS) \
	  --allowed-local-media-path /root/video \
	  --trust-remote-code \
	  --host 0.0.0.0 \
	  --port 8000
	@echo "vLLM started on port $(VLLM_PORT) (model loading takes ~20 min)"

deploy: build-app
	@echo "Creating pod for shared networking..."
	@podman pod exists studybuzz-pod || podman pod create --name studybuzz-pod -p $(APP_PORT):5000 -p $(VLLM_PORT):8000
	@echo "Starting vLLM in pod..."
	@mkdir -p output/video uploads
	@podman ps -a --filter "name=^$(VLLM_CONTAINER)$$" --format "{{.Names}}" | grep -q $(VLLM_CONTAINER) && podman rm -f $(VLLM_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(VLLM_CONTAINER) \
	  --device nvidia.com/gpu=all \
	  --ipc=host \
	  -v $(HUGGINGFACE_CACHE_PATH):/root/.cache/huggingface \
	  -v $(PWD)/output/video:/root/video \
	  docker.io/vllm/vllm-openai:latest \
	  --model Qwen/Qwen3-VL-235B-A22B-Thinking-FP8 \
	  --served-model-name Qwen3-VL \
	  --enable-expert-parallel \
	  --swap-space 16 \
	  --max-num-seqs 512 \
	  --gpu-memory-utilization 0.9 \
	  --tensor-parallel-size $(NUM_GPUS) \
	  --allowed-local-media-path /root/video \
	  --trust-remote-code \
	  --host 0.0.0.0 \
	  --port 8000
	@echo "Starting StudyBuzz app in pod..."
	@podman ps -a --filter "name=^$(APP_CONTAINER)$$" --format "{{.Names}}" | grep -q $(APP_CONTAINER) && podman rm -f $(APP_CONTAINER) || true
	podman run -d \
	  --pod studybuzz-pod \
	  --name $(APP_CONTAINER) \
	  -v $(PWD)/uploads:/app/uploads:Z \
	  -v $(PWD)/output:/app/output:Z \
	  -v $(WHISPER_PATH):/opt/whisper:ro \
	  -e PATH="/opt/whisper:$$PATH" \
	  $(APP_IMAGE)
	@echo ""
	@echo "Deployment complete!"
	@echo "StudyBuzz: http://localhost:$(APP_PORT)"
	@echo "vLLM API:  http://localhost:$(VLLM_PORT)"

clean:
	@echo "Removing containers..."
	-podman rm -f $(APP_CONTAINER)
	-podman rm -f $(VLLM_CONTAINER)
	-podman pod rm -f studybuzz-pod 2>/dev/null || true
	@echo "All containers and pod removed"
