# WisprFlow Substitute — Build Plan

## 1. Goal

Build a lightweight Windows desktop dictation tool that:

- Records audio from the microphone
- Sends it to a fast transcription model
- Does minimal AI-powered cleanup (punctuation, grammar, filler words, capitalization)
- Pastes the result wherever the cursor is currently focused

---

## 2. Architecture

### 2.1 Pipeline

Two-model pipeline: Whisper handles transcription, a fast LLM handles cleanup. Both run on Groq in serial.

### 2.2 Model Stack

| Step | Model | Notes |
|------|-------|-------|
| Transcription | `whisper-large-v3-turbo` (Groq) | 216x real-time speed, strong PT-BR accuracy |
| Cleanup | `openai/gpt-oss-20b` (Groq) | 1,000–1,200 t/s, $0.10/M input, `Reasoning: low` in system prompt |

### 2.3 Tech Stack

- **Language:** Python
- **Audio:** `pyaudio` + `webrtcvad`
- **API:** Groq Python SDK
- **UI:** `PySide6` frameless window
- **Hotkey:** `keyboard` library

---

## 3. Recording Behavior

### 3.1 Silence-Based Chunking

Recording keeps running until the user releases the hotkey. Silence triggers mid-recording chunks dispatched to Groq in parallel:

- **2s of silence** → flush the current buffer and send as a chunk
- **3s minimum chunk length** — shorter chunks are held and merged into the next one
- Results are appended in order as they return
- Strip leading silence from each chunk before upload to avoid Groq's 10-second minimum billing window

### 3.2 Activation Modes

Two modes on the same hotkey:

- **Tap** — starts on tap, stops on second tap; silence chunking runs throughout
- **Hold** — runs while key is held, releases on key-up; silence still triggers mid-recording chunks

---

## 4. Latency Optimizations

### 4.1 Record in WAV at 16 kHz

No conversion step needed. Whisper was trained on 16 kHz; record natively in WAV at that rate.

### 4.2 Warm HTTP Connections

Instantiate the Groq SDK client once at app startup and reuse it for every request. The SDK uses `httpx` under the hood with HTTP/2 and connection pooling — the first request pays the TCP+TLS handshake (~50–150ms), all subsequent ones reuse the open connection. Never instantiate the client per request.

### 4.3 Sending Chunks to the LLM Mid-Recording

Send a chunk to `gpt-oss-20b` only if its transcript ends with a sentence-terminating punctuation mark (`.`, `?`, `!`). If it doesn't, hold the fragment and prepend it to the next chunk's transcript before cleanup. This avoids asking the LLM to fix grammar on an incomplete sentence while still parallelizing cleanup with ongoing recording.

---

## 5. UX & Feedback

A thin full-width dark bar pinned to the top of the screen, always-on-top, containing a centered real-time waveform. Disappears entirely when idle.

| State | Visual |
|-------|--------|
| Idle | Hidden |
| Recording | Live waveform reflecting mic amplitude |
| Processing | Waveform frozen at last frame, slow pulse animation on top |
| Error | Red bar, tooltip with reason on hover |

Sound cues (click on start, pop on stop) complement the visual.

---

## 6. Language Handling

A `LANGUAGES` env variable accepts a comma-separated list of languages the user speaks.

**Whisper:** supports a single `language` parameter that improves transcription accuracy. If `LANGUAGES` contains exactly one entry, it is passed directly. If more than one, it is omitted and Whisper auto-detects per chunk.

**LLM:** always receives the language list in the system prompt regardless of count, so it knows what to expect and can respond in the correct language.

### System Prompt

```
You are a transcription cleanup assistant. Clean up the following transcription by fixing punctuation, grammar, and capitalization, and removing filler words (uh, um, like, etc.). Do not rephrase, summarize, or add anything. Return only the cleaned text with no explanation.

Detect the language of the input and respond in that same language.
[if LANGUAGES is set] → append: "The user may speak any of the following languages: {LANGUAGES}."
```

---

## 7. Configuration (`.env`)

```env
# API
GROQ_API_KEY=

# Models
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
CLEANUP_MODEL=openai/gpt-oss-20b

# Languages (comma-separated — 1 entry also sets Whisper's language parameter)
LANGUAGES=Portuguese,English

# Hotkey
HOTKEY=Ctrl+Shift+Space

# Silence / chunking
SILENCE_THRESHOLD=0.01      # webrtcvad aggressiveness: 0–3
SILENCE_DURATION=2.0        # seconds of silence before flushing a chunk
MIN_CHUNK_DURATION=3.0      # minimum chunk length in seconds
```
