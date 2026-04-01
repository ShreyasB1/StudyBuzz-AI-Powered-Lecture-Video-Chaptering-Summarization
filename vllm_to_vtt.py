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
            # vLLM Whisper only supports "text" and "json" formats.
            # "verbose_json" with timestamp_granularities is NOT implemented.
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="json",
                language=language,
            )

        text_content = None
        segments = []

        if isinstance(transcription, dict):
            text_content = transcription.get("text")
            segments = transcription.get("segments") or []
        elif hasattr(transcription, "model_dump"):
            dump = transcription.model_dump()
            text_content = dump.get("text")
            segments = dump.get("segments") or []
        elif hasattr(transcription, "text"):
            text_content = transcription.text
            if hasattr(transcription, "segments") and transcription.segments:
                segments = transcription.segments

        if not text_content and not segments:
            text_content = str(transcription) if transcription else ""

        text_content = (text_content or "").strip()

        if not text_content and not segments:
            print("[CRITICAL ERROR] Whisper returned empty transcription.", file=sys.stderr)
            sys.exit(1)

        print("WEBVTT\n")

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
                print(f"{(text or '').strip()}\n")
        else:
            print(
                "[INFO] Whisper returned plain text (no segment timestamps).",
                file=sys.stderr,
            )
            print(f"00:00:00.000 --> 99:59:59.000")
            print(f"{text_content}\n")

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
