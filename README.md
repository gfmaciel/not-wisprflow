# not-wisprflow

Lightweight Windows dictation tool. Press a hotkey, speak, and cleaned text pastes wherever your cursor is.

## How it works

not-wisprflow has two processing modes:

### Dual mode

1. **Record** — mic audio at 16 kHz captured in 30ms frames
2. **Chunk** — webrtcvad silence detection flushes speech segments mid-recording
3. **Transcribe** — chunks are sent to the configured transcription model in parallel
4. **Clean up** — the merged transcript is sent to the configured cleanup model
5. **Paste** — cleanup tokens are typed at the active cursor as they stream in

### Mono mode

1. **Record + chunk** — same local audio pipeline
2. **Process in order** — each WAV chunk is sent directly to one audio-capable OpenAI or Gemini model; calls are sequential so unfinished text can become context for the next chunk, but they begin as soon as chunks close while the user is still speaking
3. **Transcribe + clean + score** — the model returns cleaned text for the current chunk plus a `completion_score` from 0 to 1 indicating whether the combined thought is semantically complete
4. **Paste incrementally** — if the score is at or above `MONO_PASTE_THRESHOLD`, the buffered thought is pasted immediately; otherwise the text is held and a short trailing excerpt is supplied to the next chunk as context
5. **Flush on stop** — any remaining low-confidence text is pasted when recording ends so speech is never discarded merely because the final thought looks incomplete

The context sent back to the model is only a trailing excerpt (`MONO_CONTEXT_CHARS`); the full unresolved text stays local. The model is explicitly instructed to transcribe only the current audio chunk and not repeat previous context.

Mono mode removes the separate transcription-to-cleanup API hop. Dual mode remains available when dedicated speech-to-text plus a separate cleanup model gives better quality, latency, or cost for your setup.

## Requirements

- Windows 10/11
- Python 3.10+
- API key for whichever provider(s) your selected models use:
  - Groq
  - OpenAI
  - Gemini

## Setup

```bash
git clone https://github.com/gfmaciel/not-wisprflow.git
cd not-wisprflow
python -m pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and set the required API key(s) and models.

## Run

```bash
python main.py
```

**Hotkey (default `Alt+\`):**
- **Tap** — press once to start, press again to stop
- **Hold** — hold to record, release to stop

## Model selection

The recommended model syntax is:

```text
provider:model
```

Supported provider prefixes are `groq:`, `openai:`, and `gemini:`.

This makes provider routing explicit and lets each dual-mode stage use a different provider without code changes.

Examples:

```env
# OpenAI transcription + Gemini cleanup
PROCESSING_MODE=dual
TRANSCRIPTION_MODEL=openai:gpt-4o-mini-transcribe
CLEANUP_MODEL=gemini:gemini-3.6-flash

# Gemini transcription + OpenAI cleanup
PROCESSING_MODE=dual
TRANSCRIPTION_MODEL=gemini:gemini-3.6-flash
CLEANUP_MODEL=openai:gpt-5-mini

# One OpenAI audio model does transcription + cleanup + semantic completion scoring
PROCESSING_MODE=mono
MONO_MODEL=openai:gpt-audio-mini
MONO_PASTE_THRESHOLD=0.90

# One Gemini model does the same
PROCESSING_MODE=mono
MONO_MODEL=gemini:gemini-3.6-flash
MONO_PASTE_THRESHOLD=0.90
```

Raw legacy model names still work in dual mode with `PRIMARY_PROVIDER=groq|openai`, including the existing OpenAI/Groq fallback behavior.

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROCESSING_MODE` | `dual` | `dual` = transcription then cleanup; `mono` = one audio model does both |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Dual-mode transcription model. Prefer `provider:model` |
| `CLEANUP_MODEL` | `openai/gpt-oss-20b` | Dual-mode cleanup model. Prefer `provider:model` |
| `MONO_MODEL` | `openai:gpt-audio-mini` | Audio-capable OpenAI/Gemini model used in mono mode |
| `MONO_PASTE_THRESHOLD` | `0.90` | Paste immediately when the model's semantic completion score reaches this value |
| `MONO_CONTEXT_CHARS` | `500` | Max trailing characters of unresolved text sent as context with the next chunk |
| `MONO_TEMPERATURE` | `0.0` | Sampling temperature for mono transcription/cleanup/scoring |
| `MONO_LOG_SCORES` | `false` | Log score, threshold, paste decision, and buffer size for calibration |
| `GROQ_API_KEY` | optional | Required when a selected stage uses Groq |
| `OPENAI_API_KEY` | optional | Required when a selected stage uses OpenAI |
| `GEMINI_API_KEY` | optional | Required when a selected stage uses Gemini |
| `PRIMARY_PROVIDER` | `groq` | Legacy dual-mode provider selection for raw model names |
| `OPENAI_TRANSCRIPTION_MODEL` | `whisper-1` | Legacy OpenAI transcription model/fallback |
| `OPENAI_CLEANUP_MODEL` | `gpt-4o-mini` | Legacy OpenAI cleanup model/fallback |
| `LANGUAGES` | `Portuguese,English` | Comma-separated languages |
| `HOTKEY` | `alt+\` | Activation hotkey |
| `SILENCE_THRESHOLD` | `1` | webrtcvad aggressiveness (0–3) |
| `SILENCE_DURATION` | `2.0` | Seconds of silence before flushing a chunk |
| `MIN_CHUNK_DURATION` | `3.0` | Minimum chunk length in seconds |

`completion_score` is intentionally treated as an operational ranking rather than a calibrated probability. Enable `MONO_LOG_SCORES=true` while testing and adjust `MONO_PASTE_THRESHOLD` from observed false-early-paste vs. unnecessary-wait tradeoffs.

## Provider behavior

- **OpenAI transcription:** uses the Audio Transcriptions endpoint.
- **OpenAI cleanup:** uses Chat Completions with text input.
- **OpenAI mono:** sends base64 WAV as `input_audio`. Because `gpt-audio`/`gpt-audio-mini` support function calling but not Structured Outputs, mono forces an `emit_transcript_result` function call carrying `text` + `completion_score`.
- **Gemini transcription:** sends inline WAV audio plus a transcription instruction.
- **Gemini cleanup:** sends text with the cleanup system instruction and supports streaming.
- **Gemini mono:** sends inline WAV audio and uses Gemini structured JSON output for `text` + `completion_score`.
- **Groq:** remains supported for dual-mode transcription and cleanup, including the existing OpenAI/Groq legacy fallback.

## Tests

```bash
pytest tests/ -v
```
