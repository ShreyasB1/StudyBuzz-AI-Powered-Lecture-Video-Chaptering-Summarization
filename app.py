import os
import sys
import json
import subprocess
import uuid
import hashlib
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import threading
import urllib.request
import urllib.error
import psycopg
from init_db import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
from search import search_chapters
import base64

BASE_DIR = Path(__file__).parent.absolute()
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app, resources={r"/api/*": {"origins": "*"}})


class OnDemandPathMiddleware:
    """Strip Open OnDemand's /node/<host>/<port> prefix so Flask sees clean paths."""

    def __init__(self, wsgi_app):
        self.app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/node/"):
            parts = path.split("/")
            if len(parts) >= 4:
                actual_path = "/" + "/".join(parts[4:]) if len(parts) > 4 else "/"
                environ["PATH_INFO"] = actual_path
                environ["SCRIPT_NAME"] = "/".join(parts[:4])
        return self.app(environ, start_response)


app.wsgi_app = OnDemandPathMiddleware(app.wsgi_app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "output"
ALLOWED_EXTENSIONS = {"mp4", "mkv", "mov", "avi", "webm", "flv", "m4v", "mpeg"}

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

jobs = {}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _check_service(url):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return "ready" if resp.status == 200 else "not ready"
    except Exception:
        return "not ready"


def _hash_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _process_video(job_id, video_path, video_basename):
    base_name = os.path.splitext(video_basename)[0]
    log_path = OUTPUT_FOLDER / f"{job_id}_pipeline.log"

    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = "Starting pipeline..."
        jobs[job_id]["log_file"] = str(log_path.name)

        print(f"[Job {job_id[:8]}] Starting pipeline for {video_basename}", flush=True)
        print(f"[Job {job_id[:8]}] Pipeline log: {log_path}", flush=True)

        cmd = [
            sys.executable,
            str(BASE_DIR / "timeStampGen.py"),
            str(video_path),
            "-o",
            str(OUTPUT_FOLDER),
        ]

        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== StudyBuzz Pipeline Log ===\n")
            log_file.write(f"Job ID: {job_id}\n")
            log_file.write(f"Video: {video_basename}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write(f"{'=' * 40}\n\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(BASE_DIR),
                bufsize=1,
            )

            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                print(f"[Job {job_id[:8]}] {line.rstrip()}", flush=True)

                stripped = line.strip()
                if stripped.startswith("Converting"):
                    jobs[job_id]["progress"] = "Extracting audio (FFmpeg)..."
                elif stripped.startswith("Transcribing"):
                    jobs[job_id]["progress"] = "Transcribing audio (Whisper)..."
                elif stripped.startswith("Sending transcript"):
                    jobs[job_id]["progress"] = "Generating chapters (Mistral)..."
                elif stripped.startswith("Splitting"):
                    jobs[job_id]["progress"] = "Creating video clips..."
                elif stripped.startswith("Requesting summary"):
                    jobs[job_id]["progress"] = "Summarizing chapters (Mistral)..."
                elif "Pipeline stopped" in stripped:
                    jobs[job_id]["progress"] = stripped
                elif "Pipeline finished" in stripped:
                    jobs[job_id]["progress"] = "Pipeline finished!"

            process.wait()

            log_file.write(f"\n{'=' * 40}\n")
            log_file.write(f"Exit code: {process.returncode}\n")

        video_hash = _hash_file(video_path)
        video_out_dir = OUTPUT_FOLDER / video_hash

        transcript_path = video_out_dir / "full_transcript.vtt"
        timestamps_path = video_out_dir / "timestamps.txt"
        summary_path = video_out_dir / "chapters_summary.json"

        has_transcript = transcript_path.exists() and transcript_path.stat().st_size > 0
        has_timestamps = timestamps_path.exists() and timestamps_path.stat().st_size > 0
        has_summary = summary_path.exists() and summary_path.stat().st_size > 0

        if has_timestamps and has_summary:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = "Processing complete!"
            jobs[job_id]["files"] = {
                "transcript": f"{video_hash}/full_transcript.vtt",
                "timestamps": f"{video_hash}/timestamps.txt",
                "summary": f"{video_hash}/chapters_summary.json",
                "video_basename": video_basename,
                "video_hash": video_hash,
            }
        elif has_transcript:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["progress"] = "Pipeline failed after transcription"
            jobs[job_id]["error"] = (
                "Transcription succeeded but chapter/summary generation failed. "
                "Are the Mistral and Whisper model servers running? "
                "Check health status and pipeline log."
            )
        else:
            jobs[job_id]["status"] = "failed"
            log_tail = ""
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8").strip().split("\n")
                log_tail = "\n".join(lines[-10:])
            jobs[job_id]["error"] = (
                "Pipeline produced no output files. "
                "Are the Mistral and Whisper model servers running? "
                f"Check health status. Last log lines:\n{log_tail}"
            )
            jobs[job_id]["progress"] = "Pipeline failed - no output produced"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = f"Pipeline error: {e}"
        print(f"[Job {job_id[:8]}] Exception: {e}", flush=True)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.route("/api/videos", methods=["GET"])
def list_db_videos():
    conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT video_hash, video_name, video_date, done_processing 
                    FROM lecture_videos 
                    ORDER BY video_date DESC
                    """
                )
                rows = cur.fetchall()

        videos = [
            {
                "video_hash": row[0],
                "video_name": row[1],
                "video_date": row[2].isoformat() if row[2] else None,
                "done_processing": row[3],
            }
            for row in rows
        ]
        return jsonify({"videos": videos}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@app.route("/api/results/hash/<video_hash>", methods=["GET"])
def get_results_by_hash(video_hash):
    video_out_dir = OUTPUT_FOLDER / video_hash
    if not video_out_dir.exists():
        return jsonify({"error": "Video results not found"}), 404

    results = {}

    transcript_path = video_out_dir / "full_transcript.vtt"
    if transcript_path.exists():
        results["transcript"] = transcript_path.read_text(encoding="utf-8")

    timestamps_path = video_out_dir / "timestamps.txt"
    if timestamps_path.exists():
        lines = timestamps_path.read_text(encoding="utf-8").strip().split("\n")
        results["timestamps"] = [
            {"time": l.split(" - ")[0].strip(), "title": l.split(" - ")[1].strip()}
            for l in lines
            if " - " in l
        ]

    summary_path = video_out_dir / "chapters_summary.json"
    if summary_path.exists():
        try:
            results["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results["summary"] = []

    # We don't have the original upload name unless we query the DB, but we can guess the extension.
    # Looking for source_video.*
    source_video = next(video_out_dir.glob("source_video.*"), None)
    results["video_filename"] = (
        source_video.name if source_video else "source_video.mp4"
    )
    results["video_hash"] = video_hash

    return jsonify(results), 200


@app.route("/api/video/hash/<video_hash>", methods=["GET"])
def stream_video_by_hash(video_hash):
    video_out_dir = OUTPUT_FOLDER / video_hash
    if not video_out_dir.exists():
        return jsonify({"error": "Video directory not found"}), 404

    source_video = next(video_out_dir.glob("source_video.*"), None)
    if not source_video or not source_video.exists():
        return jsonify({"error": "Video file not found in output directory"}), 404

    return send_file(str(source_video), mimetype="video/mp4")


@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not _allowed_file(file.filename):
        return (
            jsonify(
                {
                    "error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                }
            ),
            400,
        )

    mistral_status = _check_service("http://localhost:8000/health")
    whisper_status = _check_service("http://localhost:8001/health")
    embedder_status = _check_service("http://localhost:8002/health")
    if (
        mistral_status != "ready"
        or whisper_status != "ready"
        or embedder_status != "ready"
    ):
        return (
            jsonify(
                {
                    "error": f"Model servers not ready yet. Mistral: {mistral_status}, Whisper: {whisper_status}, Nemotron: {embedder_status}. "
                    "Please wait for models to finish loading and try again."
                }
            ),
            503,
        )

    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    video_path = UPLOAD_FOLDER / filename
    file.save(str(video_path))

    jobs[job_id] = {
        "status": "uploaded",
        "filename": filename,
        "progress": "Video uploaded successfully",
    }

    thread = threading.Thread(
        target=_process_video, args=(job_id, video_path, filename), daemon=True
    )
    thread.start()

    return (
        jsonify(
            {
                "job_id": job_id,
                "filename": filename,
                "message": "Video uploaded and processing started",
            }
        ),
        202,
    )


@app.route("/api/status/<job_id>", methods=["GET"])
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id]), 200


@app.route("/api/results/<job_id>", methods=["GET"])
def get_results(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed yet", "status": job["status"]}), 400

    files = job.get("files", {})
    results = {}

    transcript_path = OUTPUT_FOLDER / files.get("transcript", "")
    if transcript_path.exists():
        results["transcript"] = transcript_path.read_text(encoding="utf-8")

    timestamps_path = OUTPUT_FOLDER / files.get("timestamps", "")
    if timestamps_path.exists():
        lines = timestamps_path.read_text(encoding="utf-8").strip().split("\n")
        results["timestamps"] = [
            {"time": l.split(" - ")[0].strip(), "title": l.split(" - ")[1].strip()}
            for l in lines
            if " - " in l
        ]

    summary_path = OUTPUT_FOLDER / files.get("summary", "")
    if summary_path.exists():
        results["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))

    results["video_filename"] = files.get("video_basename", "")
    return jsonify(results), 200


@app.route("/api/video/<job_id>", methods=["GET"])
def stream_video(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    filename = jobs[job_id].get("filename")
    if not filename:
        return jsonify({"error": "Video file not found"}), 404
    video_path = UPLOAD_FOLDER / filename
    if not video_path.exists():
        return jsonify({"error": "Video file not found on server"}), 404
    return send_file(str(video_path), mimetype="video/mp4")


@app.route("/api/health", methods=["GET"])
def health_check():
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "studybuzz",
                "mistral": _check_service("http://localhost:8000/health"),
                "whisper": _check_service("http://localhost:8001/health"),
                "nemotron": _check_service("http://localhost:8002/health"),
            }
        ),
        200,
    )


@app.route("/api/gpu-status", methods=["GET"])
def gpu_status():
    """Return live GPU memory and utilization from nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.free,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return jsonify({"error": "nvidia-smi failed", "stderr": result.stderr.strip()}), 500

        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 7:
                mem_used = int(parts[2])
                mem_total = int(parts[4])
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "memory_used_mb": mem_used,
                        "memory_free_mb": int(parts[3]),
                        "memory_total_mb": mem_total,
                        "memory_pct": round(mem_used / mem_total * 100, 1) if mem_total else 0,
                        "utilization_pct": int(parts[5]),
                        "temperature_c": int(parts[6]),
                    }
                )
        return jsonify({"gpus": gpus, "count": len(gpus)}), 200
    except FileNotFoundError:
        return jsonify({"error": "nvidia-smi not found — not running on a GPU node"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return (
        jsonify(
            {
                jid: {
                    "status": j["status"],
                    "filename": j.get("filename"),
                    "progress": j.get("progress"),
                }
                for jid, j in jobs.items()
            }
        ),
        200,
    )


@app.route("/api/ask", methods=["POST"])
def ask_question():
    """
    Endpoint for a conversational Q&A. 
    1. Uses `search_chapters` to embed and find top 3 matches.
    2. Retrieves transcripts and frames from those chapters.
    3. Sends them to Mistral to generate a localized answer.
    """
    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "Missing 'question' in request body"}), 400

    question = data["question"]
    db_conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

    # 1/2. Use existing search.py function to embed and fetch top chapters
    try:
        top_matches = search_chapters(question, limit=3)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 500

    if not top_matches:
        return jsonify({"answer": "I couldn't find any relevant information in the uploaded lectures to answer your question."})

    # 3. Retrieve transcripts and frames for those top chapters
    context_text = ""
    messages_content = []

    # The prompt instructing Mistral what to do
    messages_content.append({
        "type": "text",
        "text": (
            "You are StudyBuzz, an AI teaching assistant. Based ONLY on the following lecture transcripts and images, "
            "provide a concise answer to the student's question. If the answer is not in "
            f"the provided context, say 'I cannot answer this based on the lecture material.'\n\nStudent's Question: {question}\n\n"
        )
    })

    sources = []
    for match in top_matches:
        video_hash = match["video_hash"]
        video_name = match["video_name"]
        chapter_path = match["chapter_path"]
        similarity = match["similarity"]
        
        # Ensure we construct the absolute path correctly based on the relative path saved in the DB
        # Note: In timeStampGen.py, it's saved as f"{video_hash}/chapter_0X_title"
        chapter_dir = OUTPUT_FOLDER / chapter_path
        transcript_file = chapter_dir / "transcript.vtt"
        frames_dir = chapter_dir / "frames"

        transcript_text = ""
        if transcript_file.exists():
            # Grab just the plain text (no VTT headers/timestamps to save tokens)
            raw_vtt = transcript_file.read_text(encoding="utf-8")
            lines = [l.strip() for l in raw_vtt.splitlines() if l.strip() and not l.startswith("WEBVTT") and "-->" not in l]
            transcript_text = "\n".join(lines)
        
        context_text += f"\n--- Source: {video_name} (Relevant Chapter) ---\n{transcript_text}\n"

        sources.append({
            "video_name": video_name,
            "chapter_path": chapter_path, # useful if you want a button to click and jump to this chapter
            "similarity_score": round(similarity, 3)
        })

        # Append all extracted scene-change frames from this chapter
        if frames_dir.exists():
            frame_files = sorted(frames_dir.glob("*.png"))
            for frame_file in frame_files:
                with open(frame_file, "rb") as f:
                    frame_b64 = base64.b64encode(f.read()).decode("utf-8")
                    messages_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{frame_b64}"}
                    })

    # Add the text context we built to the message payload
    messages_content.append({"type": "text", "text": f"\nLecture Transcripts:\n{context_text}"})

    payload = {
        "model": "mistral-large",
        "messages": [{"role": "user", "content": messages_content}],
        "temperature": 0.3
    }

    # 4. Generate Answer via Mistral
    try:
        req = urllib.request.Request(
            "http://localhost:8000/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            answer_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            # mistral can output thoughts wrapped in <think>, so strip them.
            answer_text = answer_text.split("</think>")[-1].strip()
    except Exception as e:
         return jsonify({"error": f"Failed to generate answer from Mistral: {e}"}), 500

    return jsonify({
        "answer": answer_text,
        "sources": sources
    }), 200

@app.route("/api/search", methods=["POST"])
def search_endpoint():
    """
    Endpoint for purely matching a query to video chapters.
    Returns the top N matching chapters without passing them through Mistral for a combined answer.
    """
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    query = data["query"]
    limit = data.get("limit", 5)
    
    try:
        limit = int(limit)
    except ValueError:
        limit = 5

    try:
        top_matches = search_chapters(query, limit=limit)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 500

    results = []
    for match in top_matches:
        results.append({
            "video_hash": match["video_hash"],
            "video_name": match["video_name"],
            "chapter_path": match["chapter_path"],
            "similarity_score": round(match["similarity"], 4)
        })

    return jsonify({
        "query": query,
        "results": results
    }), 200

@app.route("/api/log/<job_id>", methods=["GET"])
def get_pipeline_log(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    log_file = jobs[job_id].get("log_file")
    if not log_file:
        return jsonify({"error": "No log file for this job"}), 404
    log_path = OUTPUT_FOLDER / log_file
    if not log_path.exists():
        return jsonify({"error": "Log file not found"}), 404
    return jsonify({"log": log_path.read_text(encoding="utf-8")}), 200


# ---------------------------------------------------------------------------
# Frontend serving (single-page static HTML)
# ---------------------------------------------------------------------------


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


if __name__ == "__main__":
    print("=" * 60)
    print("StudyBuzz - Integrated Server")
    print("=" * 60)
    print(f"Base directory:  {BASE_DIR}")
    print(f"Uploads folder:  {UPLOAD_FOLDER}")
    print(f"Output folder:   {OUTPUT_FOLDER}")
    print(f"Static folder:   {STATIC_DIR}")
    print("=" * 60)
    print("Starting server on http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
