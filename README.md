# not-wisprflow

Lightweight Windows dictation tool. Press a hotkey, speak, and cleaned text pastes wherever your cursor is.

## How it works

1. **Record** — mic audio at 16 kHz captured in 30ms frames
2. **Chunk** — webrtcvad silence detection flushes speech segments mid-recording
3. **Transcribe** — each chunk sent to Groq Whisper in parallel
4. **Clean up** — complete sentences cleaned by LLM (punctuation, grammar, filler words)
5. **Paste** — result pasted at active cursor via Ctrl+V

## Requirements

- Windows 10/11
- Python 3.10+
- [Groq API key](https://console.groq.com)

## Setup

```bash
git clone https://github.com/gfmaciel/not-wisprflow.git
cd not-wisprflow
python -m pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and set `GROQ_API_KEY`.

## Run

```bash
python main.py
```

**Hotkey (default `Ctrl+Shift+Space`):**
- **Tap** — press once to start, press again to stop
- **Hold** — hold to record, release to stop

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Your Groq API key |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Groq Whisper model |
| `CLEANUP_MODEL` | `openai/gpt-oss-20b` | LLM cleanup model |
| `LANGUAGES` | `Portuguese,English` | Comma-separated languages |
| `HOTKEY` | `ctrl+shift+space` | Activation hotkey |
| `SILENCE_THRESHOLD` | `1` | webrtcvad aggressiveness (0–3) |
| `SILENCE_DURATION` | `2.0` | Seconds of silence before flushing a chunk |
| `MIN_CHUNK_DURATION` | `3.0` | Minimum chunk length in seconds |

## Tests

```bash
pytest tests/ -v
```
