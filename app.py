"""
INTEGRATED Flask backend that serves BOTH the React frontend AND the API.


DEPLOYMENT STEPS:
1. Build React: cd frontend/video-summarizer-ui && npm run build
2. Run this file: python app.py
3. Access via OnDemand: https://ondemand-ice.pace.gatech.edu/node/PutYourHostHere/5000/

This server provides:
- Static React frontend at /
- REST API endpoints at /api/*
- Video processing pipeline
- File serving for results
"""

import os
import json
import subprocess
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading

# Determine base directory and React build folder
BASE_DIR = Path(__file__).parent.absolute()
REACT_BUILD_DIR = BASE_DIR / "frontend" / "video-summarizer-ui" / "build"

# Create Flask app with static folder configured for React build
app = Flask(
    __name__,
    static_folder=str(REACT_BUILD_DIR),
    static_url_path=''
)

# CORS still enabled for development flexibility
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================================================
# MIDDLEWARE: Handle OnDemand path prefix
# ============================================================================
from werkzeug.middleware.proxy_fix import ProxyFix

class OnDemandPathMiddleware:
    """
    Middleware to handle OnDemand's path prefix structure.
    OnDemand forwards requests as /node/<node>/<port>/<actual_path>
    This strips the prefix so Flask sees clean paths.
    """
    def __init__(self, app, node_name=None, port=None):
        self.app = app
        self.node_name = node_name
        self.port = port
        
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        
        # Check if path starts with /node/
        if path.startswith('/node/'):
            parts = path.split('/')
            # Path structure: /node/<node-name>/<port>/<actual-path>
            if len(parts) >= 4:
                # Strip /node/<node>/<port> prefix
                actual_path = '/' + '/'.join(parts[4:]) if len(parts) > 4 else '/'
                environ['PATH_INFO'] = actual_path
                environ['SCRIPT_NAME'] = '/'.join(parts[:4])
        
        return self.app(environ, start_response)

# Apply middleware
app.wsgi_app = OnDemandPathMiddleware(app.wsgi_app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configuration
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "output"
ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'mov', 'avi', 'webm', 'flv', 'm4v', 'mpeg'}

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Store job status in memory
jobs = {}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_video_async(job_id, video_path, video_basename):
    """Run timeStampGen.py as a subprocess in the background."""
    try:
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['progress'] = 'Starting pipeline...'
        
        # Run the timeStampGen.py script
        cmd = [
            'python',
            str(BASE_DIR / 'timeStampGen.py'),
            str(video_path),
            '-o',
            str(OUTPUT_FOLDER)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
        
        if result.returncode == 0:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 'Processing complete!'
            
            # Store paths to generated files
            base_name = os.path.splitext(video_basename)[0]
            jobs[job_id]['files'] = {
                'transcript': f"{base_name}.wav.vtt",
                'timestamps': f"{base_name}_timestamps.txt",
                'summary': f"{base_name}_summary.json",
                'video_basename': video_basename
            }
        else:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = result.stderr
            
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)


# ============================================================================
# API ENDPOINTS (all prefixed with /api/)
# ============================================================================

@app.route('/node/<path:node_path>/api/upload', methods=['POST'])
@app.route('/api/upload', methods=['POST'])
def upload_video_with_prefix():
    """Handle video upload (with OnDemand path prefix support)."""
    return upload_video()

def upload_video():
    """Handle video upload and start processing."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    video_path = UPLOAD_FOLDER / filename
    file.save(str(video_path))
    
    # Initialize job status
    jobs[job_id] = {
        'status': 'uploaded',
        'filename': filename,
        'progress': 'Video uploaded successfully'
    }
    
    # Start processing in background thread
    thread = threading.Thread(
        target=process_video_async,
        args=(job_id, video_path, filename)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'job_id': job_id,
        'filename': filename,
        'message': 'Video uploaded and processing started'
    }), 202


@app.route('/node/<path:node_path>/api/status/<job_id>', methods=['GET'])
@app.route('/api/status/<job_id>', methods=['GET'])
def get_status_with_prefix(job_id, node_path=None):
    """Get the current status of a processing job."""
    return get_status(job_id)

def get_status(job_id):
    """Get the current status of a processing job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(jobs[job_id]), 200


@app.route('/node/<path:node_path>/api/results/<job_id>', methods=['GET'])
@app.route('/api/results/<job_id>', methods=['GET'])
def get_results_with_prefix(job_id, node_path=None):
    """Get all results for a completed job."""
    return get_results(job_id)

def get_results(job_id):
    """Get all results for a completed job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    if job['status'] != 'completed':
        return jsonify({'error': 'Job not completed yet', 'status': job['status']}), 400
    
    files = job.get('files', {})
    results = {}
    
    # Read transcript
    transcript_path = OUTPUT_FOLDER / files.get('transcript', '')
    if transcript_path.exists():
        with open(transcript_path, 'r', encoding='utf-8') as f:
            results['transcript'] = f.read()
    
    # Read timestamps
    timestamps_path = OUTPUT_FOLDER / files.get('timestamps', '')
    if timestamps_path.exists():
        with open(timestamps_path, 'r', encoding='utf-8') as f:
            timestamps_lines = f.read().strip().split('\n')
            results['timestamps'] = [
                {'time': line.split(' - ')[0].strip(), 'title': line.split(' - ')[1].strip()}
                for line in timestamps_lines if ' - ' in line
            ]
    
    # Read summary
    summary_path = OUTPUT_FOLDER / files.get('summary', '')
    if summary_path.exists():
        with open(summary_path, 'r', encoding='utf-8') as f:
            results['summary'] = json.load(f)
    
    results['video_filename'] = files.get('video_basename', '')
    
    return jsonify(results), 200


@app.route('/node/<path:node_path>/api/video/<job_id>', methods=['GET'])
@app.route('/api/video/<job_id>', methods=['GET'])
def stream_video_with_prefix(job_id, node_path=None):
    """Stream the original uploaded video for playback."""
    return stream_video(job_id)

def stream_video(job_id):
    """Stream the original uploaded video for playback."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    filename = job.get('filename')
    
    if not filename:
        return jsonify({'error': 'Video file not found'}), 404
    
    video_path = UPLOAD_FOLDER / filename
    
    if not video_path.exists():
        return jsonify({'error': 'Video file not found on server'}), 404
    
    return send_file(str(video_path), mimetype='video/mp4')


@app.route('/node/<path:node_path>/api/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health_check_with_prefix(node_path=None):
    """Simple health check endpoint."""
    return health_check()

def health_check():
    """Simple health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'video-summarizer-integrated'}), 200


@app.route('/node/<path:node_path>/api/jobs', methods=['GET'])
@app.route('/api/jobs', methods=['GET'])
def list_jobs_with_prefix(node_path=None):
    """List all jobs (useful for debugging)."""
    return list_jobs()

def list_jobs():
    """List all jobs (useful for debugging)."""
    return jsonify({
        job_id: {
            'status': job['status'],
            'filename': job.get('filename'),
            'progress': job.get('progress')
        }
        for job_id, job in jobs.items()
    }), 200


# FRONTEND SERVING (React static files)

@app.route('/node/<path:node_path>/', defaults={'subpath': ''})
@app.route('/node/<path:node_path>/<path:subpath>')
def serve_react_ondemand(node_path, subpath=''):
    """
    Serve React static files with OnDemand path prefix.
    OnDemand routes: /node/<node>/<port>/<actual_path>
    """
    return serve_react(subpath)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    """
    Serve React static files.
    
    - If path matches a file in build directory, serve it
    - Otherwise, serve index.html (for React Router)
    """
    # Handle API requests separately (shouldn't reach here)
    if path.startswith('api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    
    # Serve static files
    if path != "" and (REACT_BUILD_DIR / path).exists():
        return send_from_directory(str(REACT_BUILD_DIR), path)
    else:
        return send_from_directory(str(REACT_BUILD_DIR), 'index.html')


if __name__ == '__main__':
    print("=" * 70)
    print("🚀 VIDEO SUMMARIZER - INTEGRATED SERVER")
    print("=" * 70)
    print(f"📁 Base directory: {BASE_DIR}")
    print(f"📤 Uploads folder: {UPLOAD_FOLDER}")
    print(f"📥 Output folder: {OUTPUT_FOLDER}")
    print(f"🎬 timeStampGen.py: {BASE_DIR / 'timeStampGen.py'}")
    print(f"⚛️  React build folder: {REACT_BUILD_DIR}")
    print("=" * 70)
    
    if not REACT_BUILD_DIR.exists():
        print("⚠️  WARNING: React build folder not found!")
        print(f"   Expected at: {REACT_BUILD_DIR}")
        print("   Please run these commands first:")
        print("   1. cd frontend/video-summarizer-ui")
        print("   2. npm run build")
        print("=" * 70)
    else:
        print("✅ React build folder found")
        print("=" * 70)
    
    print("🌐 Starting server on http://0.0.0.0:5000")
    print("🔗 Access via OnDemand:")
    print("   https://ondemand-ice.pace.gatech.edu/node/PutYourHostHere/5000/")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
