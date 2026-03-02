import sys
import argparse
from openai import OpenAI


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


def generate_vtt(audio_path, host_ip, port, model_name, language):
    base_url = f"http://{host_ip}:{port}/v1"
    client = OpenAI(base_url=base_url, api_key="EMPTY")

    print(f"[INFO] Connecting to {base_url}...", file=sys.stderr)
    print(
        f"[INFO] Requesting model: '{model_name}' (Language: {language})",
        file=sys.stderr,
    )

    try:
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                language=language,  # <--- CRITICAL FIX: Explicitly set language
            )

        print("WEBVTT\n")

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

                print(f"{vtt_start} --> {vtt_end}")
                print(f"{text.strip()}\n")
        else:
            print(
                "[WARNING] Response did not contain segments. The server might not support segment-level timestamps.",
                file=sys.stderr,
            )
            text_content = ""
            if isinstance(transcription, dict):
                text_content = transcription.get("text", str(transcription))
            elif hasattr(transcription, "text"):
                text_content = transcription.text
            else:
                text_content = str(transcription)
            print(f"00:00:00.000 --> 00:00:00.000\n{text_content.strip()}\n")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Could not transcribe.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate VTT from vLLM Whisper")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--host", default="localhost", help="IP address of Podman host")
    parser.add_argument("--port", default="8000", help="Port mapped in Podman")
    parser.add_argument("--model", default="whisper", help="Served model name")
    parser.add_argument(
        "--lang",
        default="en",
        help="Language code (en, es, fr) - REQUIRED to fix validation error",
    )

    args = parser.parse_args()

    generate_vtt(args.audio_file, args.host, args.port, args.model, args.lang)
