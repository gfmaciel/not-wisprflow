# not-wisprflow

Lightweight Windows dictation tool. Press a hotkey, speak, and cleaned text pastes wherever your cursor is.

## How it works

1. **Record** — mic audio at 16 kHz captured in 30ms frames
2. **Chunk** — webrtcvad silence detection flushes speech segments mid-recording
3. **Transcribe** — each chunk sent to the configured Whisper provider in parallel (with automatic fallback)
4. **Clean up** — complete sentences cleaned by LLM (punctuation, grammar, filler words)
5. **Paste** — cleanup tokens are typed at the active cursor as they stream in, so the first characters appear as soon as the LLM starts emitting (instead of waiting for the full response). If streaming fails before any output, the tool falls back to clipboard + Ctrl+V. Keep the target window focused after releasing the hotkey, since incremental typing goes wherever focus lands.

## Requirements

- Windows 10/11
- Python 3.10+
- [Groq API key](https://console.groq.com) — required when `PRIMARY_PROVIDER=groq` (default)
- [OpenAI API key](https://platform.openai.com/api-keys) — required when `PRIMARY_PROVIDER=openai`; optional as fallback

## Setup

```bash
git clone https://github.com/gfmaciel/not-wisprflow.git
cd not-wisprflow
python -m pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and set the required API key(s) for your chosen provider.

## Run

```bash
python main.py
```

**Hotkey (default `Alt+\`):**
- **Tap** — press once to start, press again to stop
- **Hold** — hold to record, release to stop

## Provider & Fallback

not-wisprflow supports **Groq** and **OpenAI** for both transcription and LLM cleanup. Set `PRIMARY_PROVIDER` to choose which runs first. If the primary provider fails on any request, the other is tried automatically and a message is printed to the console. If the primary provider's API key is missing at startup but the other key is configured, the app switches automatically and logs a warning.

| Setup | `PRIMARY_PROVIDER` | Required key | Optional fallback key |
|---|---|---|---|
| Groq primary (default) | `groq` | `GROQ_API_KEY` | `OPENAI_API_KEY` |
| OpenAI primary | `openai` | `OPENAI_API_KEY` | `GROQ_API_KEY` |

If only one key is configured the tool works with that provider alone (no fallback).

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIMARY_PROVIDER` | `groq` | Primary AI provider (`groq` or `openai`) |
| `GROQ_API_KEY` | *(required if Groq is primary)* | Your Groq API key |
| `OPENAI_API_KEY` | *(required if OpenAI is primary)* | Your OpenAI API key |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Groq Whisper model |
| `CLEANUP_MODEL` | `openai/gpt-oss-20b` | Groq LLM cleanup model (try `llama-3.1-8b-instant` for lower latency at some quality cost) |
| `OPENAI_TRANSCRIPTION_MODEL` | `whisper-1` | OpenAI Whisper model |
| `OPENAI_CLEANUP_MODEL` | `gpt-4o-mini` | OpenAI LLM cleanup model |
| `LANGUAGES` | `Portuguese,English` | Comma-separated languages |
| `HOTKEY` | `alt+\` | Activation hotkey |
| `SILENCE_THRESHOLD` | `1` | webrtcvad aggressiveness (0–3) |
| `SILENCE_DURATION` | `2.0` | Seconds of silence before flushing a chunk |
| `MIN_CHUNK_DURATION` | `3.0` | Minimum chunk length in seconds |

## Tests

```bash
pytest tests/ -v
```
