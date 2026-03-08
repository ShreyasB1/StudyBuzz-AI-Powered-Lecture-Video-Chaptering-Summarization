import subprocess
import os
import json
import argparse
import glob
import re
import base64
import shutil
import tempfile
import hashlib
from typing import Optional
from urllib import request, error
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg
import openai
from init_db import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT


def _sanitize_title(title: str) -> str:
    """Normalize a chapter title into a safe filesystem-friendly slug."""
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title
    )
    return safe_title.strip().replace(" ", "_")


def convert_video_to_mp3(video_path: str, output_path: str) -> bool:
    """
    Converts a video file to an MP3 audio file using ffmpeg.

    This function executes an ffmpeg command to extract the audio stream from a
    given video file and saves it as a heavily compressed MP3 file to adhere
    to Whisper size limits. It assumes that ffmpeg is installed and accessible
    in the system's PATH.

    Args:
        video_path: The absolute or relative path to the input video file.
        output_path: The absolute or relative path where the output .mp3 file
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
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-q:a",
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


def format_timestamp(seconds: float) -> str:
    """
    Converts seconds (float) to WebVTT format (HH:MM:SS.mmm).
    """
    if seconds is None:
        return "00:00:00.000"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


def transcribe_audio_with_whisper(mp3_path: str, output_txt_path: str) -> bool:
    """
    Transcribes an MP3 audio file to text using VLLM Whisper API.

    Args:
        mp3_path: The absolute or relative path to the input .mp3 file.
        output_txt_path: The absolute or relative path where the output .txt
                         transcript will be saved.

    Returns:
        True if the transcription was successful, False otherwise.
    """
    # 1. Input Validation: Check if the source MP3 file exists.
    if not os.path.exists(mp3_path):
        print(f"Error: Input MP3 file not found at '{mp3_path}'")
        return False

    # 2. Prepare Output Directory and Path
    output_dir = os.path.dirname(output_txt_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    host_ip = "localhost"
    port = "8001"
    model_name = "whisper"
    language = "en"

    base_url = f"http://{host_ip}:{port}/v1"
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "Error: openai package is not installed. Please install it using 'pip install openai'"
        )
        return False

    client = OpenAI(base_url=base_url, api_key="EMPTY")

    print(f"Transcribing '{mp3_path}' to '{output_txt_path}' using {base_url}...")

    try:
        with open(mp3_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                language=language,
            )

        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")

            # Extract segments robustly (OpenAI client versions can return dicts or Pydantic models)
            segments = []
            if isinstance(transcription, dict):
                segments = transcription.get("segments", [])
            elif hasattr(transcription, "segments") and transcription.segments:
                segments = transcription.segments
            elif hasattr(transcription, "model_dump"):
                dump = transcription.model_dump()
                segments = dump.get("segments", [])

            if segments:
                for segment in segments:
                    if isinstance(segment, dict):
                        start = segment.get("start", 0.0)
                        end = segment.get("end", 0.0)
                        text = segment.get("text", "")
                    else:
                        start = getattr(segment, "start", 0.0)
                        end = getattr(segment, "end", 0.0)
                        text = getattr(segment, "text", "")

                    vtt_start = format_timestamp(start)
                    vtt_end = format_timestamp(end)

                    f.write(f"{vtt_start} --> {vtt_end}\n")
                    f.write(f"{text.strip()}\n\n")
            else:
                print(
                    "Warning: Response did not contain segments. The server might not support segment-level timestamps."
                )
                text_content = ""
                if isinstance(transcription, dict):
                    text_content = transcription.get("text", str(transcription))
                elif hasattr(transcription, "text"):
                    text_content = transcription.text
                else:
                    text_content = str(transcription)
                f.write(f"00:00:00.000 --> 00:00:00.000\n{text_content.strip()}\n")

        print("Transcription successful!")
        return True

    except Exception as e:
        print(f"Error during transcription: {e}")
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

        # Create safe filename and chapter folder
        safe_title = _sanitize_title(timestamp["title"])
        chapter_folder_name = f"chapter_{i+1:02d}_{safe_title}"
        chapter_folder_path = os.path.join(output_dir, chapter_folder_name)
        os.makedirs(chapter_folder_path, exist_ok=True)

        output_filename = "transcript.vtt"
        output_path = os.path.join(chapter_folder_path, output_filename)

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


def _extract_all_scene_frames(video_path: str, temp_dir: str) -> list[dict]:
    """Extracts scene change frames from the entire video, treating the output PTS as frame index."""
    if not os.path.exists(video_path):
        print(f"Warning: Video file not found at {video_path}")
        return []

    os.makedirs(temp_dir, exist_ok=True)

    # Get the frame rate to calculate seconds from frame index
    metadata = _probe_video_metadata(video_path)
    fps = metadata.get("fps")
    if not fps or fps <= 0:
        fps = 30.0  # Fallback to standard 30 fps
        print(
            f"Warning: Could not determine fps for {video_path}, defaulting to {fps} for timestamp calculation"
        )

    output_pattern = os.path.join(temp_dir, "out%d.png")

    command = [
        "ffmpeg",
        "-i",
        video_path,
        "-an",  # Disable audio processing to speed up extraction
        "-threads",
        "0",  # Use all available cores
        "-preset",
        "ultrafast",  # Maximize encoding speed
        "-vf",
        "select='eq(n\\,0)+gt(scene\\,0.05)',scale=720:-1",
        "-fps_mode",
        "vfr",
        "-frame_pts",
        "1",
        "-y",
        output_pattern,
    ]

    print(f"Extracting all scene frames from {video_path}...")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames: {e.stderr}")
        return []
    except Exception as e:
        print(f"Error processing frames: {e}")
        return []

    frames_meta = []
    frame_files = glob.glob(os.path.join(temp_dir, "out*.png"))
    for frame_file in frame_files:
        filename = os.path.basename(frame_file)
        match = re.search(r"out(\d+)\.png$", filename)
        if match:
            frame_index = int(match.group(1))
            seconds = frame_index / fps
            frames_meta.append(
                {"path": frame_file, "pts": frame_index, "seconds": seconds}
            )

    frames_meta.sort(key=lambda x: x["pts"])
    print(f"Finished extracting {len(frames_meta)} scene frames.")
    return frames_meta


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
        "-show_entries",
        "stream=avg_frame_rate,duration",
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


def summarize_chapters_with_llm(
    timestamps_path: str,
    frames_meta: list[dict],
    chapter_transcripts_dir: str,
    output_json_path: str,
    api_url: str = "http://localhost:8000/v1/chat/completions",
    model_name: str = "mistral-large",
) -> bool:
    """
    Generate summaries for each chapter using extracted video frames and a local LLM.

    Args:
        timestamps_path: Path to the timestamps file ("HH:MM:SS - Chapter Title").
        frames_meta: Metadata of all pre-extracted scene frames.
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
                        "start_sec": parse_vtt_timestamp(timestamp_str),
                    }
                )

    except IOError as e:
        print(f"Error reading timestamps file: {e}")
        return False

    if not timestamps:
        print("Error: No valid timestamps found for summarization.")
        return False

    for i in range(len(timestamps)):
        if i + 1 < len(timestamps):
            timestamps[i]["end_sec"] = timestamps[i + 1]["start_sec"]
        else:
            timestamps[i]["end_sec"] = float("inf")

    print(
        f"Preparing to summarize {len(timestamps)} chapter(s) with pre-extracted frames."
    )

    def _summarize_entry(entry: dict) -> Optional[tuple[int, dict]]:
        chapter_idx = entry["index"]
        safe_title = entry["safe_title"]
        try:
            chapter_folder_name = f"chapter_{chapter_idx:02d}_{safe_title}"
            chapter_folder_path = os.path.join(
                chapter_transcripts_dir, chapter_folder_name
            )
            transcript_filename = "transcript.vtt"
            transcript_path = os.path.join(chapter_folder_path, transcript_filename)
            if not os.path.exists(transcript_path):
                print(
                    f"Warning: Transcript file missing for chapter {chapter_idx} ({entry['title']})."
                )
                return None

            transcript_text = ""
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript_content = f.read()
                transcript_text = _extract_plain_text_from_vtt(
                    transcript_content
                ).strip()
                if not transcript_text:
                    transcript_text = transcript_content.strip()
            except IOError as e:
                print(
                    f"Warning: Could not read transcript for chapter {chapter_idx}: {e}"
                )
                return None

            chapter_frames = [
                f
                for f in frames_meta
                if entry["start_sec"] <= f["seconds"] < entry["end_sec"]
            ]
            print(
                f"Chapter {chapter_idx} ('{entry['title']}') contains {len(chapter_frames)} extracted frames."
            )

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

            user_content = [{"type": "text", "text": user_prompt_text}]

            for frame_info in chapter_frames[:32]:
                with open(frame_info["path"], "rb") as bf:
                    frame_b64 = base64.b64encode(bf.read()).decode("utf-8")

                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{frame_b64}"},
                    }
                )

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": user_content},
                ],
            }

            print(
                f"Requesting summary for chapter {chapter_idx}: {entry['title']} using {min(32, len(chapter_frames))} frames."
            )
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
                error_body = e.read().decode("utf-8")
                print(
                    f"Warning: LLM returned HTTPError {e.code} for chapter {chapter_idx}. "
                    f"Reason: {error_body[:200]}"
                )
                return None
            except error.URLError as e:
                print(
                    f"Warning: Failed to contact LLM for chapter {chapter_idx}: {e.reason}"
                )
                return None
            except Exception as e:
                print(
                    f"Warning: Unexpected error during summarization request for chapter {chapter_idx}: {e}"
                )
                return None

            summary_text = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            summary_text = summary_text.split("</think>")[-1].strip()
            if not summary_text:
                print(f"Warning: Empty summary returned for chapter {chapter_idx}.")
                return None

            summary_json_path = os.path.join(chapter_folder_path, "summary.json")
            try:
                with open(summary_json_path, "w", encoding="utf-8") as f:
                    json.dump({entry["title"]: summary_text}, f, indent=2)
            except IOError as e:
                print(f"Error writing chapter summary JSON: {e}")

            # Copy frames physically into the chapter directory
            frames_out_dir = os.path.join(chapter_folder_path, "frames")
            os.makedirs(frames_out_dir, exist_ok=True)
            for frame_info in chapter_frames:
                dest_path = os.path.join(
                    frames_out_dir, os.path.basename(frame_info["path"])
                )
                if not os.path.exists(dest_path):
                    shutil.copy2(frame_info["path"], dest_path)

            return (chapter_idx, {entry["time"]: {entry["title"]: summary_text}})
        except Exception as e:
            print(
                f"Warning: Unexpected error during summarization for chapter {chapter_idx}: {e}"
            )
            return None

    summaries = []
    max_workers = min(10, len(timestamps)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_entry = {
            executor.submit(_summarize_entry, entry): entry["index"]
            for entry in timestamps
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
    model_name = "mistral-large"
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


def generate_chapter_embeddings(
    video_hash: str,
    summary_json_path: str,
    chapter_transcripts_dir: str,
    db_conn_str: str,
    api_url: str = "http://localhost:8002/v1/embeddings",
    model_name: str = "nemotron",
) -> bool:
    """
    Generate and store vector embeddings for each chapter's combined text content.
    """
    if not os.path.exists(summary_json_path):
        print(f"Error: Summaries file not found at '{summary_json_path}'")
        return False

    try:
        with open(summary_json_path, "r", encoding="utf-8") as f:
            summaries = json.load(f)
    except Exception as e:
        print(f"Error loading summaries JSON: {e}")
        return False

    success = True
    print(f"Generating embeddings for {len(summaries)} chapter(s)...")

    for idx, chapter in enumerate(summaries, 1):
        # The summary JSON uses nested format: {timestamp: {title: summary_text}}
        # Unpack it to get the actual title and summary.
        chapter_title = f"Chapter {idx}"
        summary_text = ""
        if isinstance(chapter, dict):
            for _timestamp, title_summary in chapter.items():
                if isinstance(title_summary, dict):
                    for title, summary in title_summary.items():
                        chapter_title = title
                        summary_text = summary
                        break
                break

        safe_title = _sanitize_title(chapter_title)
        chapter_folder_name = f"chapter_{idx:02d}_{safe_title}"
        chapter_folder_path = os.path.join(chapter_transcripts_dir, chapter_folder_name)

        # We need the relative path for the database logic
        chapter_rel_path = f"{video_hash}/{chapter_folder_name}"

        transcript_path = os.path.join(chapter_folder_path, "transcript.vtt")
        transcript_text = ""

        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript_content = f.read()
                transcript_text = _extract_plain_text_from_vtt(
                    transcript_content
                ).strip()
                if not transcript_text:
                    transcript_text = transcript_content.strip()
            except IOError as e:
                print(f"Warning: Could not read transcript for chapter {idx}: {e}")

        # Combine transcript and summary exclusively for this chapter
        combined_text = f"Chapter Title: {chapter_title}\n\nSummary:\n{summary_text}\n\nTranscript:\n{transcript_text}"

        try:
            client = openai.OpenAI(
                base_url=api_url.rsplit("/embeddings", 1)[0], api_key="empty"
            )

            response = client.embeddings.create(model=model_name, input=combined_text)

            embedding_vector = response.data[0].embedding

            # Store to Postgres
            with psycopg.connect(db_conn_str, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chapter_embeddings (video_hash, chapter_path, model_name, embedding)
                        VALUES (%s, %s, %s, %s::vector)
                        ON CONFLICT (video_hash, chapter_path, model_name) 
                        DO UPDATE SET embedding = EXCLUDED.embedding
                        """,
                        (
                            video_hash,
                            chapter_rel_path,
                            model_name,
                            embedding_vector,
                        ),
                    )
            print(f"  ✓ Saved '{model_name}' embedding for Chapter {idx}")
        except Exception as e:
            print(f"  ✗ Failed to generate/store embedding for chapter {idx}: {e}")
            success = False

    return success


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
        print(f"\nComputing SHA-256 hash for {video_path}...")
        sha256_hash = hashlib.sha256()
        try:
            with open(video_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            video_hash = sha256_hash.hexdigest()
        except IOError as e:
            print(f"Error reading video file to hash: {e}")
            return

        video_out_dir = os.path.join(output_dir, video_hash)
        os.makedirs(video_out_dir, exist_ok=True)

        # Log to Database
        conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
        video_basename = os.path.basename(video_path)
        try:
            with psycopg.connect(conn_str, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO lecture_videos (video_hash, folder_path, video_name, done_processing)
                        VALUES (%s, %s, %s, FALSE)
                        ON CONFLICT (video_hash) 
                        DO UPDATE SET done_processing = FALSE, folder_path = EXCLUDED.folder_path, video_name = EXCLUDED.video_name
                        """,
                        (video_hash, video_out_dir, video_basename),
                    )
            print(f"Logged video {video_hash} to database as processing.")
        except Exception as e:
            print(f"Warning: Failed to log video to database: {e}")

        # Copy original video into the hash folder
        original_ext = os.path.splitext(video_path)[1]
        copied_video_path = os.path.join(video_out_dir, f"source_video{original_ext}")
        if os.path.abspath(video_path) != os.path.abspath(
            copied_video_path
        ) and not os.path.exists(copied_video_path):
            print(f"Copying source video to output directory...")
            shutil.copy2(video_path, copied_video_path)

        # Optional: We could point `video_path` to `copied_video_path` so subsequent tools use the local copy, but the original is fine.

        out_audio = os.path.join(video_out_dir, "audio.mp3")
        out_transcript = os.path.join(video_out_dir, "full_transcript.vtt")
        out_timestamps = os.path.join(video_out_dir, "timestamps.txt")
        chapter_dir = video_out_dir
        frames_dir = os.path.join(video_out_dir, "all_frames_temp")
        summary_json_path = os.path.join(video_out_dir, "chapters_summary.json")

        print(f"Processing video into: {video_out_dir}")

        # Start extracting frames in the background
        with ThreadPoolExecutor(max_workers=2) as pipeline_executor:
            frames_future = pipeline_executor.submit(
                _extract_all_scene_frames, video_path, frames_dir
            )

            transcript_exists = os.path.exists(out_transcript)

            if transcript_exists:
                print(
                    f"Transcript already exists at '{out_transcript}'. "
                    "Skipping audio conversion and transcription."
                )
                if not os.path.exists(out_audio):
                    print(
                        f"Note: MP3 file '{out_audio}' is missing. Continuing with existing transcript."
                    )
            else:
                if os.path.exists(out_audio):
                    print(f"Existing MP3 found at '{out_audio}'. Skipping conversion.")
                else:
                    print("-" * 20)
                    if not convert_video_to_mp3(video_path, out_audio):
                        print("Pipeline stopped at video-to-MP3 conversion.")
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

            # 5. Wait for frames
            print("-" * 20)
            print("Waiting for background frame extraction to complete...")
            try:
                frames_meta = frames_future.result()
            except Exception as e:
                print(f"Pipeline stopped: Frame extraction failed with error: {e}")
                return

            # 6. Summarize each chapter with the LLM and write JSON output
            print("-" * 20)
            if not summarize_chapters_with_llm(
                out_timestamps,
                frames_meta,
                chapter_dir,
                summary_json_path,
            ):
                print("Pipeline stopped at chapter summarization.")
                return

            # 7. Generate Nemotron Embeddings for semantic search
            print("-" * 20)
            if not generate_chapter_embeddings(
                video_hash, summary_json_path, chapter_dir, conn_str
            ):
                print(
                    "Warning: Chapter embedding generation encountered errors, but continuing to finalize."
                )

        # 8. Mark as complete in database
        try:
            with psycopg.connect(conn_str, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE lecture_videos SET done_processing = TRUE WHERE video_hash = %s",
                        (video_hash,),
                    )
            print("Successfully marked video as done_processing in database.")
        except Exception as e:
            print(f"Warning: Failed to update database status: {e}")

        # 9. Cleanup scratch files
        print("Cleaning up scratch files...")
        if os.path.exists(out_audio):
            try:
                os.remove(out_audio)
                print(f"Deleted {out_audio}")
            except OSError as e:
                print(f"Warning: Failed to delete {out_audio}: {e}")

        if os.path.exists(frames_dir):
            try:
                shutil.rmtree(frames_dir)
                print(f"Deleted {frames_dir}")
            except OSError as e:
                print(f"Warning: Failed to delete {frames_dir}: {e}")

        print("\n--- Pipeline finished for this file ---")
        print(f"Video Hash: {video_hash}")
        print(f"Chapter transcripts: {chapter_dir}")
        print(f"Pre-extracted Frames: {frames_dir}")
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
