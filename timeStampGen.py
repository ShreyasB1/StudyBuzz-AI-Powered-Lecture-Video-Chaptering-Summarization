import subprocess
import os
import json
import argparse
import glob
import re
import base64
import shutil
import cv2
from typing import Optional
from urllib import request, error
from concurrent.futures import ThreadPoolExecutor, as_completed


def _sanitize_title(title: str) -> str:
    """Normalize a chapter title into a safe filesystem-friendly slug."""
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title
    )
    return safe_title.strip().replace(" ", "_")


def split_video(
    video_path: str, start_time: str, end_time: str, output_path: str
) -> bool:
    """
    Splits a video file from a starting time to an ending time using ffmpeg.

    This function extracts a segment of a video file between the specified
    start and end times and saves it to a new file, re-encoding to a
    stream-friendly H.264/AAC format so downstream video loaders can reliably
    decode a consistent number of frames.

    Args:
        video_path: The absolute or relative path to the input video file.
        start_time: The starting timestamp in format "HH:MM:SS" or "MM:SS" or seconds.
        end_time: The ending timestamp in format "HH:MM:SS" or "MM:SS" or seconds.
        output_path: The absolute or relative path where the output video file
                     will be saved. The directory will be created if it
                     doesn't exist.

    Returns:
        True if the split was successful, False otherwise.
    """
    # 1. Input Validation: Check if the source video file exists.
    if not os.path.exists(video_path):
        print(f"Error: Input video file not found at '{video_path}'")
        return False

    # 2. Prepare Output Directory: Ensure the directory for the output file exists.
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 3. Construct the ffmpeg command.
    # Re-encode the segment to ensure compatibility with downstream video loaders.
    command = [
        "ffmpeg",
        "-ss",
        start_time,  # Start time
        "-to",
        end_time,  # End time
        "-i",
        video_path,  # Input file
        "-c:v",
        "libx264",  # Re-encode video for consistent decoding
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",  # Overwrite output file if exists
        output_path,
    ]

    # 4. Execute the command.
    print(f"Splitting '{video_path}' from {start_time} to {end_time}...")
    print(f"Output will be saved to '{output_path}'")
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("Video split successful!")
        return True
    except FileNotFoundError:
        print("Error: 'ffmpeg' command not found.")
        print("Please ensure ffmpeg is installed and in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print("Error during video splitting.")
        print(f"ffmpeg returned non-zero exit status: {e.returncode}")
        print("ffmpeg stderr:", e.stderr)
        return False


def convert_video_to_wav(video_path: str, output_path: str) -> bool:
    """
    Converts a video file to a WAV audio file using ffmpeg.

    This function executes an ffmpeg command to extract the audio stream from a
    given video file and saves it as an uncompressed WAV file. It assumes that
    ffmpeg is installed and accessible in the system's PATH.

    Args:
        video_path: The absolute or relative path to the input video file.
        output_path: The absolute or relative path where the output .wav file
                     will be saved. The directory will be created if it
                     doesn't exist.

    Returns:
        True if the conversion was successful, False otherwise.
    """
    # 1. Input Validation: Check if the source video file exists.
    if not os.path.exists(video_path):
        print(f"Error: Input video file not found at '{video_path}'")
        return False

    # 2. Prepare Output Directory: Ensure the directory for the output file exists.
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 3. Construct the ffmpeg command.
    command = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-y",
        output_path,
    ]

    # 4. Execute the command.
    print(f"Converting '{video_path}' to '{output_path}'...")
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("Conversion successful!")
        return True
    except FileNotFoundError:
        print("Error: 'ffmpeg' command not found.")
        print("Please ensure ffmpeg is installed and in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print("Error during conversion.")
        print(f"ffmpeg returned non-zero exit status: {e.returncode}")
        print("ffmpeg stderr:", e.stderr)
        return False


def transcribe_audio_with_whisper(wav_path: str, output_txt_path: str) -> bool:
    """
    Transcribes a WAV audio file to text using whisper-cli.

    This function executes a whisper-cli command to transcribe the audio from a
    given WAV file and saves the output to a text file. It assumes that
    whisper-cli is installed and accessible in the system's PATH and that the
    specified model file is in the same directory as this script.

    Args:
        wav_path: The absolute or relative path to the input .wav file.
        output_txt_path: The absolute or relative path where the output .txt
                         transcript will be saved.

    Returns:
        True if the transcription was successful, False otherwise.
    """
    # 1. Input Validation: Check if the source WAV file exists.
    if not os.path.exists(wav_path):
        print(f"Error: Input WAV file not found at '{wav_path}'")
        return False

    # 2. Model Path: Locate the Whisper model file.
    model_name = "ggml-large-v3-turbo.bin"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, model_name)

    if not os.path.exists(model_path):
        print(f"Error: Whisper model not found at '{model_path}'")
        print("Please ensure the model file is in the same directory as the script.")
        return False

    # 3. Prepare Output Directory and Path
    output_dir = os.path.dirname(output_txt_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    output_filename_base = os.path.splitext(output_txt_path)[0]

    # 4. Construct the whisper-cli command.
    command = [
        "whisper-cli",
        "-f",
        wav_path,
        "-m",
        model_path,
        "-ovtt",
        # "-of",
        # output_filename_base,
    ]

    # 5. Execute the command.
    output_txt_path = wav_path + ".vtt"
    print(f"Transcribing '{wav_path}' to '{output_txt_path}'...")
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, encoding="utf-8"
        )
        print("Transcription successful!")
        return True
    except FileNotFoundError:
        print("Error: 'whisper-cli' command not found.")
        print("Please ensure whisper-cli is installed and in your system's PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print("Error during transcription.")
        print(f"whisper-cli returned non-zero exit status: {e.returncode}")
        print("whisper-cli stderr:", e.stderr)
        return False


def split_transcript_by_timestamps(
    transcript_path: str, timestamps_path: str, output_dir: str
) -> bool:
    """
    Splits a transcript file into separate chapter files based on timestamps.

    This function reads a VTT transcript file and a timestamps file, then creates
    separate transcript files for each chapter based on the time ranges defined
    by the timestamps.

    Args:
        transcript_path: Path to the VTT transcript file.
        timestamps_path: Path to the timestamps file with format "HH:MM:SS - Chapter Title".
        output_dir: Directory where the chapter transcript files will be saved.

    Returns:
        True if all chapter transcripts were created successfully, False otherwise.
    """
    # 1. Input Validation: Check if files exist.
    if not os.path.exists(transcript_path):
        print(f"Error: Transcript file not found at '{transcript_path}'")
        return False

    if not os.path.exists(timestamps_path):
        print(f"Error: Timestamps file not found at '{timestamps_path}'")
        return False

    # 2. Parse timestamps file.
    timestamps = []
    try:
        with open(timestamps_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or " - " not in line:
                    continue

                parts = line.split(" - ", 1)
                if len(parts) != 2:
                    continue

                timestamp_str = parts[0].strip()
                title = parts[1].strip()

                time_parts = timestamp_str.split(":")
                if len(time_parts) not in [2, 3]:
                    print(
                        f"Warning: Skipping line {line_num} - invalid timestamp format: {timestamp_str}"
                    )
                    continue

                # Convert timestamp to seconds for comparison
                if len(time_parts) == 3:
                    hours, minutes, seconds = map(int, time_parts)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                else:
                    minutes, seconds = map(int, time_parts)
                    total_seconds = minutes * 60 + seconds

                timestamps.append(
                    {"time": timestamp_str, "seconds": total_seconds, "title": title}
                )

    except (IOError, ValueError) as e:
        print(f"Error reading timestamps file: {e}")
        return False

    if not timestamps:
        print("Error: No valid timestamps found in the file.")
        return False

    print(f"Found {len(timestamps)} chapter(s) to extract from transcript.")

    # 3. Parse VTT transcript file.
    vtt_entries = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by double newlines to get individual subtitle entries
        blocks = content.split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 2:
                continue

            # Look for timestamp line (format: 00:00:00.000 --> 00:00:05.000)
            for line in lines:
                if "-->" in line:
                    time_parts = line.split("-->")
                    if len(time_parts) == 2:
                        start_time_str = time_parts[0].strip()
                        end_time_str = time_parts[1].strip()

                        # Extract text (everything after the timestamp line)
                        text_start_idx = block.find(line) + len(line)
                        text = block[text_start_idx:].strip()

                        # Convert VTT timestamp to seconds
                        start_seconds = parse_vtt_timestamp(start_time_str)
                        end_seconds = parse_vtt_timestamp(end_time_str)

                        if start_seconds is not None and end_seconds is not None:
                            vtt_entries.append(
                                {
                                    "start": start_seconds,
                                    "end": end_seconds,
                                    "start_str": start_time_str,
                                    "end_str": end_time_str,
                                    "text": text,
                                }
                            )
                    break

    except IOError as e:
        print(f"Error reading transcript file: {e}")
        return False

    if not vtt_entries:
        print("Error: No valid VTT entries found in transcript.")
        return False

    print(f"Parsed {len(vtt_entries)} transcript entries.")

    # 4. Create output directory.
    os.makedirs(output_dir, exist_ok=True)

    # 5. Create chapter transcript files.
    success_count = 0
    for i, timestamp in enumerate(timestamps):
        start_time = timestamp["seconds"]
        # Determine end time (next timestamp or end of transcript)
        if i + 1 < len(timestamps):
            end_time = timestamps[i + 1]["seconds"]
        else:
            # Last chapter extends to the end
            end_time = float("inf")

        # Filter VTT entries for this chapter
        chapter_entries = [
            entry
            for entry in vtt_entries
            if entry["start"] >= start_time and entry["start"] < end_time
        ]

        # Create safe filename
        safe_title = _sanitize_title(timestamp["title"])
        output_filename = f"chapter_{i+1:02d}_{safe_title}.vtt"
        output_path = os.path.join(output_dir, output_filename)

        # Write chapter transcript
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("WEBVTT\n\n")
                for entry in chapter_entries:
                    f.write(f"{entry['start_str']} --> {entry['end_str']}\n")
                    f.write(f"{entry['text']}\n\n")

            print(
                f"Created chapter {i+1}/{len(timestamps)}: {timestamp['title']} ({len(chapter_entries)} entries)"
            )
            success_count += 1

        except IOError as e:
            print(f"Error writing chapter file '{output_filename}': {e}")

    # 6. Report results.
    print(f"\n--- Chapter Transcript Creation Complete ---")
    print(
        f"Successfully created {success_count}/{len(timestamps)} chapter transcripts."
    )
    print(f"Files saved to: {output_dir}")

    return success_count == len(timestamps)


def parse_vtt_timestamp(timestamp_str: str) -> float:
    """
    Parses a VTT timestamp string and converts it to seconds.

    Args:
        timestamp_str: VTT timestamp in format "HH:MM:SS.mmm" or "MM:SS.mmm"

    Returns:
        Total seconds as a float, or None if parsing fails.
    """
    try:
        # Remove any trailing/leading whitespace
        timestamp_str = timestamp_str.strip()

        # Split by '.' to separate seconds from milliseconds
        if "." in timestamp_str:
            time_part, ms_part = timestamp_str.split(".")
            milliseconds = float(f"0.{ms_part}")
        else:
            time_part = timestamp_str
            milliseconds = 0.0

        # Split time part by ':'
        parts = time_part.split(":")

        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds
        elif len(parts) == 2:
            minutes, seconds = map(int, parts)
            total_seconds = minutes * 60 + seconds + milliseconds
        else:
            return None

        return total_seconds

    except (ValueError, AttributeError):
        return None


def _extract_plain_text_from_vtt(content: str) -> str:
    """Return just the spoken text from a VTT transcript."""
    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def _encode_video_frames(
    video_path: str, frames_per_second_to_capture: int = 1
) -> list[str]:
    """Extract Base64-encoded JPEG frames from a video file."""
    if frames_per_second_to_capture <= 0:
        frames_per_second_to_capture = 1

    if not os.path.exists(video_path):
        print(f"Warning: Video file not found at {video_path}")
        return []

    video = cv2.VideoCapture(video_path)
    if not video.isOpened():
        print(f"Warning: Could not open video file {video_path}")
        return []

    encoded_frames: list[str] = []
    video_fps = video.get(cv2.CAP_PROP_FPS)
    if video_fps and video_fps > 0:
        frame_interval = max(int(video_fps // frames_per_second_to_capture), 1)
    else:
        frame_interval = 1

    frame_index = 0
    while True:
        success, frame = video.read()
        if not success:
            break

        if frame_index % frame_interval == 0:
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                encoded_frames.append(base64.b64encode(buffer).decode("utf-8"))
        frame_index += 1

    video.release()
    return encoded_frames


def _extract_timestamp_lines(text: str) -> list[str]:
    """Return only lines that match 'HH:MM[:SS] - Title'."""
    pattern = re.compile(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}\s*-\s*.+")
    matches: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if pattern.match(line):
            matches.append(line)
    return matches


def _probe_video_metadata(video_path: str) -> dict[str, Optional[float]]:
    """Return a lightweight metadata snapshot for debugging video clips."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_frames",
        "-show_entries",
        "stream=nb_read_frames,avg_frame_rate,duration",
        "-of",
        "json",
        video_path,
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        info = json.loads(result.stdout)
        stream = (info.get("streams") or [{}])[0]

        raw_frame_count = stream.get("nb_read_frames")
        frame_count = int(raw_frame_count) if raw_frame_count is not None else None

        raw_rate = stream.get("avg_frame_rate")
        fps = None
        if raw_rate and raw_rate != "0/0":
            num, den = raw_rate.split("/", 1)
            if den not in ("0", "0.0", "0/0"):
                try:
                    fps = float(num) / float(den)
                except (ValueError, ZeroDivisionError):
                    fps = None

        duration = None
        if stream.get("duration"):
            try:
                duration = float(stream["duration"])
            except (TypeError, ValueError):
                duration = None

        return {"frame_count": frame_count, "fps": fps, "duration": duration}
    except Exception as exc:
        print(f"Warning: ffprobe metadata lookup failed for '{video_path}': {exc}")
        return {"frame_count": None, "fps": None, "duration": None}


def create_clips_from_timestamps(
    video_path: str,
    timestamps_path: str,
    output_dir: str,
    mirror_dir: Optional[str] = None,
) -> bool:
    """
    Creates video clips based on timestamps from a timestamp file.

    This function reads a timestamp file containing chapter markers in the format
    "HH:MM:SS - Chapter Title" and uses the split_video function to create
    individual video clips for each chapter segment.

    Args:
        video_path: The absolute or relative path to the input video file.
        timestamps_path: Path to the timestamps file with format "HH:MM:SS - Chapter Title".
        output_dir: Directory where the video clips will be saved.
        mirror_dir: Optional directory that will receive a copy of each clip (e.g., a
            host path mounted into the vLLM container).

    Returns:
        True if all clips were created successfully, False otherwise.
    """
    # 1. Input Validation: Check if files exist.
    if not os.path.exists(video_path):
        print(f"Error: Input video file not found at '{video_path}'")
        return False

    if not os.path.exists(timestamps_path):
        print(f"Error: Timestamps file not found at '{timestamps_path}'")
        return False

    # 2. Read and parse the timestamps file.
    timestamps = []
    try:
        with open(timestamps_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and lines that don't contain timestamps
                if not line or " - " not in line:
                    continue

                # Parse timestamp format: "HH:MM:SS - Chapter Title"
                parts = line.split(" - ", 1)
                if len(parts) != 2:
                    continue

                timestamp_str = parts[0].strip()
                title = parts[1].strip()

                # Validate timestamp format (HH:MM:SS or MM:SS)
                time_parts = timestamp_str.split(":")
                if len(time_parts) not in [2, 3]:
                    print(
                        f"Warning: Skipping line {line_num} - invalid timestamp format: {timestamp_str}"
                    )
                    continue

                timestamps.append({"time": timestamp_str, "title": title})

    except IOError as e:
        print(f"Error reading timestamps file: {e}")
        return False

    if not timestamps:
        print("Error: No valid timestamps found in the file.")
        print("Expected format: 'HH:MM:SS - Chapter Title' or 'MM:SS - Chapter Title'")
        return False

    print(f"Found {len(timestamps)} chapter(s) to extract.")

    # 3. Create output directories.
    os.makedirs(output_dir, exist_ok=True)
    if mirror_dir:
        os.makedirs(mirror_dir, exist_ok=True)

    video_label = _sanitize_title(os.path.splitext(os.path.basename(video_path))[0])

    # 4. Create video clips for each timestamp segment.
    success_count = 0
    for i, timestamp in enumerate(timestamps):
        start_time = timestamp["time"]
        # Determine end time (next timestamp or end of video)
        if i + 1 < len(timestamps):
            end_time = timestamps[i + 1]["time"]
        else:
            # For the last segment, we'll need to get video duration or use a large value
            # Using a large value as end time (ffmpeg will stop at video end)
            end_time = "99:59:59"

        # Create a safe filename from the chapter title
        safe_title = _sanitize_title(timestamp["title"])

        # Get the video extension from input file
        video_ext = os.path.splitext(video_path)[1]
        output_filename = f"{video_label}_clip_{i+1:02d}_{safe_title}{video_ext}"
        output_path = os.path.join(output_dir, output_filename)

        print(f"\n--- Creating clip {i+1}/{len(timestamps)} ---")
        print(f"Title: {timestamp['title']}")
        print(f"Time range: {start_time} to {end_time}")

        if split_video(video_path, start_time, end_time, output_path):
            success_count += 1
            if mirror_dir:
                mirror_path = os.path.join(mirror_dir, output_filename)
                if os.path.abspath(mirror_path) != os.path.abspath(output_path):
                    try:
                        shutil.copy2(output_path, mirror_path)
                    except OSError as copy_err:
                        print(
                            "Warning: Failed to synchronize clip to mirror directory "
                            f"'{mirror_path}': {copy_err}"
                        )
        else:
            print(f"Failed to create clip for '{timestamp['title']}'")

    # 5. Report results.
    print(f"\n--- Clip Creation Complete ---")
    print(f"Successfully created {success_count}/{len(timestamps)} clips.")
    print(f"Clips saved to: {output_dir}")

    return success_count == len(timestamps)


def summarize_clips_with_llm(
    timestamps_path: str,
    clips_dir: str,
    chapter_transcripts_dir: str,
    output_json_path: str,
    api_url: str = "http://localhost:8000/v1/chat/completions",
    model_name: str = "Qwen3-VL",
    container_video_root: str = "/root/video",
) -> bool:
    """
    Generate summaries for each chapter clip using a local LLM.

    The function sends the text transcript plus a direct video reference by using the
    `video_url` content type with a `file://` URI to the local clip. Ensure the vLLM server is started with
    `--allowed-local-media-path` that includes `clips_dir` so the model can access
    the referenced files. As a fallback preview, sampled JPEG frames are also
    attached as inline base64 images when available.

    Args:
        timestamps_path: Path to the timestamps file ("HH:MM:SS - Chapter Title").
        clips_dir: Directory that contains chapter video clips.
        chapter_transcripts_dir: Directory with per-chapter transcript VTT files.
        output_json_path: Destination path for the JSON summaries file.
        api_url: OpenAI-compatible endpoint for the local LLM.
        model_name: Model identifier exposed by the local LLM server.

    Returns:
        True if at least one summary was generated, False otherwise.
    """
    if not os.path.exists(timestamps_path):
        print(f"Error: Timestamps file not found at '{timestamps_path}'")
        return False

    if not os.path.isdir(clips_dir):
        print(f"Error: Clips directory not found at '{clips_dir}'")
        return False

    if not os.path.isdir(chapter_transcripts_dir):
        print(
            f"Error: Chapter transcripts directory not found at '{chapter_transcripts_dir}'"
        )
        return False

    # Load timestamps
    timestamps = []
    try:
        with open(timestamps_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or " - " not in line:
                    continue

                parts = line.split(" - ", 1)
                if len(parts) != 2:
                    continue

                timestamp_str = parts[0].strip()
                title = parts[1].strip()

                if not timestamp_str:
                    continue

                timestamps.append(
                    {
                        "time": timestamp_str,
                        "title": title,
                        "safe_title": _sanitize_title(title),
                        "index": len(timestamps) + 1,
                    }
                )

    except IOError as e:
        print(f"Error reading timestamps file: {e}")
        return False

    if not timestamps:
        print("Error: No valid timestamps found for summarization.")
        return False

    print(
        f"Preparing to summarize {len(timestamps)} chapter clip(s) with video context."
    )

    def _summarize_entry(entry: dict) -> Optional[tuple[int, dict]]:
        chapter_idx = entry["index"]
        safe_title = entry["safe_title"]
        try:
            clip_pattern = os.path.join(clips_dir, f"*clip_{chapter_idx:02d}_{safe_title}*")
            matching_clips = sorted(glob.glob(clip_pattern))
            if not matching_clips:
                print(
                    f"Warning: No clip found for chapter {chapter_idx} ({entry['title']})."
                )
                return None
            clip_path = matching_clips[0]
            clip_name = os.path.basename(clip_path)

            transcript_filename = f"chapter_{chapter_idx:02d}_{safe_title}.vtt"
            transcript_path = os.path.join(chapter_transcripts_dir, transcript_filename)
            if not os.path.exists(transcript_path):
                print(
                    f"Warning: Transcript file missing for chapter {chapter_idx} ({entry['title']})."
                )
                return None

            transcript_text = ""
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript_content = f.read()
                transcript_text = _extract_plain_text_from_vtt(transcript_content).strip()
                if not transcript_text:
                    transcript_text = transcript_content.strip()
            except IOError as e:
                print(
                    f"Warning: Could not read transcript for chapter {chapter_idx}: {e}"
                )
                return None

            container_clip_path = f"{container_video_root.rstrip('/')}/{clip_name}"
            file_url = f"file://{container_clip_path}"
            user_prompt_text = (
                "Please summarize the following video chapter. Focus on the main ideas, key "
                "takeaways, and any actions described. Be concise but informative. Limit "
                "the summary to at most 2 paragraphs, less is preferable \n\n"
                f"Start Timestamp: {entry['time']}\n"
                f"Chapter Title: {entry['title']}\n\n"
                "Transcript:\n---\n"
                f"{transcript_text}\n"
                "---"
            )
            user_content = [
                {"type": "text", "text": user_prompt_text},
                {"type": "video_url", "video_url": {"url": file_url}},
            ]
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": user_content},
                ],
            }

            _ = _probe_video_metadata(clip_path)
            print(f"Requesting summary for chapter {chapter_idx}: {entry['title']}")
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                api_url, data=data, headers={"Content-Type": "application/json"}
            )

            try:
                with request.urlopen(req) as response:
                    if response.status != 200:
                        print(
                            f"Warning: LLM returned status {response.status} for chapter {chapter_idx}."
                        )
                        return None
                    response_data = json.loads(response.read().decode("utf-8"))
            except error.HTTPError as e:
                error_body = (
                    e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                )
                print(
                    "Warning: LLM returned HTTPError for chapter "
                    f"{chapter_idx} ({entry['title']}): status={e.code}, reason={e.reason}"
                )
                if error_body:
                    print("Response body snippet:")
                    print(error_body[:2000])
                return None
            except error.URLError as e:
                print(
                    f"Warning: Failed to contact LLM for chapter {chapter_idx}: {e.reason}"
                )
                return None
            except Exception as e:
                print(
                    f"Warning: Unexpected error during summarization for chapter {chapter_idx}: {e}"
                )
                return None

            summary_text = (
                response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            summary_text = summary_text.split("</think>")[-1].strip()
            if not summary_text:
                print(
                    f"Warning: Empty summary returned for chapter {chapter_idx} ({entry['title']})."
                )
                return None

            return (chapter_idx, {entry["time"]: {entry["title"]: summary_text}})
        except Exception as e:
            print(
                f"Warning: Unexpected error during summarization for chapter {chapter_idx}: {e}"
            )
            return None

    summaries = []
    max_workers = min(2, len(timestamps)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_entry = {
            executor.submit(_summarize_entry, entry): entry["index"] for entry in timestamps
        }
        for future in as_completed(future_to_entry):
            try:
                result = future.result()
            except Exception as exc:
                chapter_idx = future_to_entry[future]
                print(
                    f"Warning: Unexpected error during summarization for chapter {chapter_idx}: {exc}"
                )
                continue
            if result:
                summaries.append(result)

    if not summaries:
        print("No summaries were generated.")
        return False

    summaries.sort(key=lambda item: item[0])
    ordered_summaries = [item[1] for item in summaries]

    output_dir = os.path.dirname(output_json_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(ordered_summaries, f, indent=2)
    except IOError as e:
        print(f"Error writing summaries JSON: {e}")
        return False

    print(f"Summaries written to '{output_json_path}'.")
    return True


def generate_timestamps_with_llm(
    transcript_path: str, output_timestamps_path: str
) -> bool:
    """
    Generates video chapter timestamps from a transcript using a local LLM.

    This function sends the transcript to an OpenAI-compatible API endpoint
    (like a local vLLM server) and asks the model to generate timestamps for
    key topics, saving them to a file.

    Args:
        transcript_path: Path to the input transcript .txt file.
        output_timestamps_path: Path to save the generated timestamps.

    Returns:
        True if timestamp generation was successful, False otherwise.
    """
    # 1. Input Validation: Check if the transcript file exists.
    if not os.path.exists(transcript_path):
        print(f"Error: Transcript file not found at '{transcript_path}'")
        return False

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()
    except IOError as e:
        print(f"Error reading transcript file: {e}")
        return False

    # 2. Set up the API request details.
    api_url = "http://localhost:8000/v1/chat/completions"
    model_name = "Qwen3-VL"
    system_prompt = "You are a helpful assistant that analyzes video transcripts and generates chapter timestamps in the format 'HH:MM:SS - Chapter Title'."
    user_prompt = f"""
Based on the following video transcript, please generate a list of key topics or chapters with timestamps.
Each chapter should represent a distinct topic or a significant shift in the conversation.

The output format MUST be strictly:
HH:MM:SS - Chapter Title

Do not include any other text, explanations, or introductory phrases. Only provide the list of timestamps.

Transcript:
---
{transcript_text}
---
"""

    # 3. Construct the request payload.
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,  # Lower temperature for more deterministic, structured output
    }

    # 4. Make the API call using Python's built-in urllib.
    print(f"Sending transcript to '{model_name}' at '{api_url}'...")
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        api_url, data=data, headers={"Content-Type": "application/json"}
    )

    def _fallback_to_completions(prompt_text: str) -> Optional[str]:
        base_url = api_url.rsplit("/chat/completions", 1)[0]
        completions_url = f"{base_url}/completions"
        completion_payload = {
            "model": model_name,
            "prompt": prompt_text,
            "temperature": 0.2,
            "max_tokens": 512,
        }
        completion_data = json.dumps(completion_payload).encode("utf-8")
        completion_req = request.Request(
            completions_url,
            data=completion_data,
            headers={"Content-Type": "application/json"},
        )

        print(f"Falling back to completions endpoint at '{completions_url}'...")
        try:
            with request.urlopen(completion_req) as completion_response:
                if completion_response.status != 200:
                    print(
                        "Fallback completions endpoint returned status "
                        f"{completion_response.status}."
                    )
                    return None
                completion_json = json.loads(completion_response.read().decode("utf-8"))
                return completion_json.get("choices", [{}])[0].get("text", "")
        except error.URLError as completion_err:
            print(
                "Error connecting to the fallback completions endpoint: "
                f"{completion_err.reason}"
            )
            return None
        except Exception as completion_exc:
            print(
                f"Unexpected error during fallback completions call: {completion_exc}"
            )
            return None

    try:
        with request.urlopen(req) as response:
            if response.status == 200:
                response_data = json.loads(response.read().decode("utf-8"))
                generated_text = response_data["choices"][0]["message"]["content"]

                generated_text = generated_text.split("</think>")[-1]
                timestamp_lines = _extract_timestamp_lines(generated_text)
                if not timestamp_lines:
                    print("Warning: LLM response did not contain any valid timestamps.")
                    return False

                os.makedirs(os.path.dirname(output_timestamps_path), exist_ok=True)
                with open(output_timestamps_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(timestamp_lines))

                print("Timestamp generation successful!")
                return True
            else:
                print(f"Error: API returned status code {response.status}")
                print("Response:", response.read().decode("utf-8"))
                return False

    except error.HTTPError as e:
        error_body = (
            e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        )
        print(
            f"HTTPError from LLM server at '{api_url}': status={e.code}, reason={e.reason}"
        )
        if error_body:
            print("Response body snippet:")
            print(error_body[:2000])

        fallback_prompt = system_prompt + "\n\n" + user_prompt
        fallback_text = _fallback_to_completions(fallback_prompt)
        if fallback_text:
            fallback_text = fallback_text.split("</think>")[-1]
            timestamp_lines = _extract_timestamp_lines(fallback_text)
            if timestamp_lines:
                os.makedirs(os.path.dirname(output_timestamps_path), exist_ok=True)
                with open(output_timestamps_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(timestamp_lines))

                print(
                    "Timestamp generation successful via fallback completions endpoint!"
                )
                return True
            print("Fallback completions response contained no valid timestamp lines.")

        print("Fallback to completions endpoint failed.")
        return False
    except error.URLError as e:
        print(f"Error connecting to the LLM server at '{api_url}'. Is it running?")
        print(f"Reason: {e.reason}")

        fallback_prompt = system_prompt + "\n\n" + user_prompt
        fallback_text = _fallback_to_completions(fallback_prompt)
        if fallback_text:
            fallback_text = fallback_text.split("</think>")[-1]
            timestamp_lines = _extract_timestamp_lines(fallback_text)
            if timestamp_lines:
                os.makedirs(os.path.dirname(output_timestamps_path), exist_ok=True)
                with open(output_timestamps_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(timestamp_lines))

                print(
                    "Timestamp generation successful via fallback completions endpoint!"
                )
                return True
            print("Fallback completions response contained no valid timestamp lines.")

        return False
    except Exception as e:
        print(f"An unexpected error occurred during API call: {e}")
        fallback_prompt = system_prompt + "\n\n" + user_prompt
        fallback_text = _fallback_to_completions(fallback_prompt)
        if fallback_text:
            fallback_text = fallback_text.split("</think>")[-1]
            timestamp_lines = _extract_timestamp_lines(fallback_text)
            if timestamp_lines:
                os.makedirs(os.path.dirname(output_timestamps_path), exist_ok=True)
                with open(output_timestamps_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(timestamp_lines))

                print(
                    "Timestamp generation successful via fallback completions endpoint!"
                )
                return True
            print("Fallback completions response contained no valid timestamp lines.")

        return False


def main():
    """Main function to parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="A pipeline to convert video(s) to audio, transcribe, and generate timestamps.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="The path to a single input video file (optional if --input-dir is used).",
    )
    parser.add_argument(
        "-d",
        "--input-dir",
        help="A directory containing video files to process (non-recursive).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="The directory to save the output files. Defaults to 'output'.",
    )

    args = parser.parse_args()

    input_file = args.input_file
    input_dir = args.input_dir
    output_dir = args.output_dir

    if not input_file and not input_dir:
        parser.error(
            "Either provide an input_file or --input-dir with video files to process."
        )

    # Helper to run the pipeline for one video file
    def process_video(video_path: str) -> None:
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        out_audio = os.path.join(output_dir, f"{base_name}.wav")
        out_transcript = os.path.join(output_dir, f"{base_name}.wav.vtt")
        out_timestamps = os.path.join(output_dir, f"{base_name}_timestamps.txt")
        chapter_dir = os.path.join(output_dir, f"{base_name}_chapters")
        clips_dir = os.path.join(output_dir, "video")
        mirror_dir = os.path.join(os.getcwd(), "video")
        summary_json_path = os.path.join(output_dir, f"{base_name}_summary.json")

        os.makedirs(output_dir, exist_ok=True)

        print(f"\nProcessing: {video_path}")

        transcript_exists = os.path.exists(out_transcript)

        if transcript_exists:
            print(
                f"Transcript already exists at '{out_transcript}'. "
                "Skipping audio conversion and transcription."
            )
            if not os.path.exists(out_audio):
                print(
                    f"Note: WAV file '{out_audio}' is missing. Continuing with existing transcript."
                )
        else:
            if os.path.exists(out_audio):
                print(f"Existing WAV found at '{out_audio}'. Skipping conversion.")
            else:
                print("-" * 20)
                if not convert_video_to_wav(video_path, out_audio):
                    print("Pipeline stopped at video-to-WAV conversion.")
                    return

            print("-" * 20)
            if not transcribe_audio_with_whisper(out_audio, out_transcript):
                print("Pipeline stopped at audio transcription.")
                return

        # 3. Generate timestamps from text
        print("-" * 20)
        if not generate_timestamps_with_llm(out_transcript, out_timestamps):
            print("Pipeline stopped at timestamp generation.")
            return

        # 4. Split transcript into chapter-specific files
        print("-" * 20)
        if not split_transcript_by_timestamps(
            out_transcript, out_timestamps, chapter_dir
        ):
            print("Pipeline stopped at transcript splitting.")
            return

        # 5. Create chapter clips from original video
        print("-" * 20)
        if not create_clips_from_timestamps(
            video_path,
            out_timestamps,
            clips_dir,
            mirror_dir=mirror_dir,
        ):
            print("Pipeline stopped at clip creation.")
            return

        # 6. Summarize each clip with the LLM and write JSON output
        print("-" * 20)
        if not summarize_clips_with_llm(
            out_timestamps,
            clips_dir,
            chapter_dir,
            summary_json_path,
            container_video_root="/root/video",
        ):
            print("Pipeline stopped at clip summarization.")
            return

        print("\n--- Pipeline finished for this file ---")
        print(f"Audio file: {out_audio}")
        print(f"Transcript file: {out_transcript}")
        print(f"Timestamps file: {out_timestamps}")
        print(f"Chapter transcripts: {chapter_dir}")
        print(f"Chapter clips: {clips_dir}")
        print(f"Mirrored clips for vLLM: {mirror_dir}")
        print(f"Summary JSON: {summary_json_path}")

        try:
            with open(summary_json_path, "r", encoding="utf-8") as summary_file:
                final_summary = json.load(summary_file)
            print("\nFinal chapter summaries:")
            print(json.dumps(final_summary, indent=2, ensure_ascii=False))
        except IOError as e:
            print(f"Warning: Unable to read summary JSON for display: {e}")

    # If an input directory is provided, iterate its video files
    if input_dir:
        if not os.path.isdir(input_dir):
            print(f"Error: input directory not found at '{input_dir}'")
            return

        # Common video extensions
        video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".mpeg"}
        entries = sorted(os.listdir(input_dir))
        videos = [
            os.path.join(input_dir, e)
            for e in entries
            if os.path.isfile(os.path.join(input_dir, e))
            and os.path.splitext(e)[1].lower() in video_exts
        ]

        if not videos:
            print(f"No supported video files found in directory '{input_dir}'.")
            return

        for vid in videos:
            process_video(vid)

    # If a single input file is provided, process it
    if input_file:
        if not os.path.isfile(input_file):
            print(f"Error: input file not found at '{input_file}'")
            return
        process_video(input_file)


if __name__ == "__main__":
    main()
