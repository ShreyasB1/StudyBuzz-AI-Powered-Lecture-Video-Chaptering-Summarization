import os
import json
import subprocess
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import threading
import urllib.request
import urllib.error

BASE_DIR = Path(__file__).parent.absolute()
STATIC_DIR = BASE_DIR / "static"

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static"
)
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


def _process_video(job_id, video_path, video_basename):
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = "Starting pipeline..."

        cmd = [
            "python",
            str(BASE_DIR / "timeStampGen.py"),
            str(video_path),
            "-o",
            str(OUTPUT_FOLDER),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(BASE_DIR)
        )

        if result.returncode == 0:
            base_name = os.path.splitext(video_basename)[0]
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = "Processing complete!"
            jobs[job_id]["files"] = {
                "transcript": f"{base_name}.mp3.vtt",
                "timestamps": f"{base_name}_timestamps.txt",
                "summary": f"{base_name}_summary.json",
                "video_basename": video_basename,
            }
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = result.stderr or result.stdout
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not _allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    video_path = UPLOAD_FOLDER / filename
    file.save(str(video_path))

    jobs[job_id] = {
        "status": "uploaded",
        "filename": filename,
        "progress": "Video uploaded successfully",
    }

    thread = threading.Thread(target=_process_video, args=(job_id, video_path, filename), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "filename": filename, "message": "Video uploaded and processing started"}), 202


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
    return jsonify({
        "status": "healthy",
        "service": "studybuzz",
        "mistral": _check_service("http://localhost:8000/health"),
        "whisper": _check_service("http://localhost:8001/health"),
    }), 200


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return jsonify({
        jid: {"status": j["status"], "filename": j.get("filename"), "progress": j.get("progress")}
        for jid, j in jobs.items()
    }), 200


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
