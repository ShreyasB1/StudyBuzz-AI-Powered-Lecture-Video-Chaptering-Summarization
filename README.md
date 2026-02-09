# M-SB-TUT-Stud-1
This branch holds the code for running the video summary pipeline.

There are may components in this codebase:

# VLLM
VLLM is used for running the large language model. 
We are using [Qwen3-VL-235B](https://huggingface.co/Qwen/Qwen3-VL-235B-A22B-Thinking-FP8).

We use podman to run the VLLM server. We choose podman over a conventional local pip install to avoid dependency issues.

The command to run the VLLM server is as follows:

```bash
podman run --device nvidia.com/gpu=all \
 -v ~/M-SB-TUT-Stud-1/huggingface:/root/.cache/huggingface \
 -v $(pwd)/video:/root/video \
 -p 8000:8000 \
 --ipc=host \
 docker.io/vllm/vllm-openai:latest \
 -e VLLM_USE_DEEP_GEMM=0 \
 --model Qwen/Qwen3-VL-235B-A22B-Thinking-FP8 \
 --served-model-name Qwen3-VL \
 --enable-expert-parallel \
 --swap-space 16 \
 --max-num-seqs 512 \
 --gpu-memory-utilization 0.9 \
 --tensor-parallel-size 8 \
 --allowed-local-media-path /root/video \
 --trust-remote-code \
 --host 0.0.0.0 \
 --port 8000
 ```

The VLLM server will be accessible at `http://localhost:8000`. It takes 20 minutes to start up. 
There are a few important flags to note:
- `--allowed-local-media-path /root/video`: This flag allows the model to access images and videos from the specified path. 
- `-v $(pwd)/video:/root/video`: This mounts the local `video` directory to the container's `/root/video` directory.
- `--tensor-parallel-size 8`: This flag sets the tensor parallelism size, we use 8 H200 GPUs.
- `-v ~/M-SB-TUT-Stud-1/huggingface:/root/.cache/huggingface`: This mounts the local huggingface cache to the container to avoid re-downloading the model. Change the path as necessary.

The command must be run in the output directory (create it if it does not exist) where the `timeStampGen.py` script will output the intermediate files. There must also be a video directory in the output directory where the input video is stored.

# Video Summary Pipeline
The main code for the video summary pipeline is in `timeStampGen.py`. This script takes a video file as input and outputs a text summary of the video. It uses the VLLM server to run the Qwen3-VL model for video understanding. The VLLM server must be running before executing this script.

This script also requires a few other dependencies. 

## FFmpeg
FFmpeg is used for video processing. A binary must be on the system PATH for the script to work. 

## whisper.cpp
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) is used for audio transcription. It is a C++ implementation of the Whisper model. The binary must also be on the system PATH. The binary the script uses is `whisper-cli`. It must be compiled with GPU support for reasonable performance. The model we used can be found in this repository: `ggml-large-v3-turbo.bin`.

There is sometimes a problem compiling this on the cluster, changing `-march=native` to `-march=x86-64-v3` in `whisper.cpp/ggml/src/ggml-cpu/CMakeLists.txt` helps at times.

## Python Dependencies
We recommend creating a virtual environment for the python dependencies. The dependencies can be installed using the `requirements.txt` file in this directory:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run:
```bash
timeStampGen.py --help
``` 
to see the usage of the script. The main arguments are:
```
usage: timeStampGen.py [-h] [-d INPUT_DIR] [-o OUTPUT_DIR] [input_file]
timeStampGen.py: error: Either provide an input_file or --input-dir with video files to process.
```

A sample command to run the script is as follows:
```bash
python timeStampGen.py lecture.mp4
```
