# not-wisprflow

A lightweight Windows dictation app. Use a global hotkey to record speech, transcribe it with an AI model, clean up the text, and paste the result into the active text field.

The app runs in the system tray. A small waveform appears at the top of the screen while recording or processing and disappears when idle.

## Requirements

- Windows 10 or 11, with a working microphone
- **Python 3.13** — the only version tested in GitHub Actions (older versions are not currently verified by CI)
- API keys for the providers selected in your configuration

**Default dual-mode setup:** OpenAI transcribes with `gpt-transcribe`; Groq cleans with `openai/gpt-oss-20b`. This requires **both** `OPENAI_API_KEY` and `GROQ_API_KEY`. You can change either model in `.env` without changing Python source.

## Install (Windows PowerShell)

1. Install [Python 3.13](https://www.python.org/downloads/) and Git if needed.
2. Open PowerShell and run:

```powershell
git clone https://github.com/gfmaciel/not-wisprflow.git
cd not-wisprflow
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

3. Enter your `OPENAI_API_KEY` and `GROQ_API_KEY`. Keep the default models or explicitly select the providers you want.
4. Save `.env`, then double-click **`start.bat`** in the project directory.

The launcher prefers `.venv\Scripts\pythonw.exe`, then `venv\Scripts\pythonw.exe`, then an installed windowless Python launcher. It starts **only on demand**; it does not create a startup entry, scheduled task, or background service. Windows may briefly show a command window while opening the batch file, but no terminal remains open.

For errors, check `not-wisprflow.log`. To run in a terminal:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Use

The default shortcut is **Alt + \**. It works globally, including when another application has focus.

- **Tap:** tap once to begin recording; tap again to stop.
- **Hold:** hold for more than 0.5 seconds to record; release to stop.
- **Quit:** right-click the system-tray icon and select **Quit**.

The hotkey uses one non-suppressing keyboard hook. It does not consume or rewrite the shortcut; the focused app may also react to those keys. A Windows named mutex prevents duplicate running instances.

**Paste target:** The result is pasted **once, after processing**, into the text field that has focus **at that time**, even if you switched windows while recording. There is no focus-lock or `SAFE_PASTE_TARGET` setting. The app copies the final text to the clipboard and sends **Ctrl + V**; your previous clipboard content is replaced.

## Processing modes

### Dual mode (default)

1. Record 16 kHz mono audio in 30 ms frames through the default microphone.
2. Detect pauses with WebRTC VAD. Short speech chunks can be held until more audio is available.
3. Transcribe WAV chunks in parallel with the selected transcription provider.
4. Merge the transcriptions **in spoken order** and send the result to the separate cleanup model.
5. Buffer the cleanup response and paste the completed result once.

The cleanup prompt preserves meaning, tone, and language; fixes punctuation, spelling, and clearly unnecessary filler words; and applies clear requests to edit or format the *transcript itself*. Questions, content requests, and external actions are **transcribed**, not carried out. The model is instructed not to invent an email subject, greeting, recipient, signature, or list entry. These are model instructions, not a guarantee of perfect text output.

### Mono mode

1. Record and chunk audio through the same local pipeline.
2. Send chunks **sequentially** to one audio-capable OpenAI or Gemini model. It returns `text` and a `completion_score` for the combined thought.
3. Keep incomplete text locally and pass only its trailing excerpt (`MONO_CONTEXT_CHARS`) as context for the next chunk. The model is instructed not to repeat that excerpt.
4. Buffer complete and incomplete text, then **paste once after processing ends**. The threshold does **not** trigger early keystrokes.

`completion_score` is a model-generated estimate, not a calibrated probability. Groq is not supported for mono mode.

## Choose models

Prefer the explicit `provider:model` format:

```dotenv
# Default: OpenAI transcription + Groq cleanup
PROCESSING_MODE=dual
TRANSCRIPTION_MODEL=openai:gpt-transcribe
CLEANUP_MODEL=openai/gpt-oss-20b
PRIMARY_PROVIDER=groq
```

The cleanup model above has an **unprefixed legacy Groq model ID**: `/` is part of the model name, not a provider separator. To select a different provider explicitly, use a colon:

```dotenv
# Example: OpenAI for both dual-mode stages (only OPENAI_API_KEY needed)
TRANSCRIPTION_MODEL=openai:gpt-transcribe
CLEANUP_MODEL=openai:gpt-4o-mini

# Alternative: one model for both tasks (only OPENAI_API_KEY needed)
PROCESSING_MODE=mono
MONO_MODEL=openai:gpt-audio-mini
```

Supported provider prefixes are `openai:`, `groq:`, and `gemini:` for dual mode; mono mode supports OpenAI or Gemini. Models must support the required audio or text API.

Legacy raw model names still route via `PRIMARY_PROVIDER` in dual mode. Some legacy **transcription** configurations can fall back between OpenAI and Groq when both are configured. **Cleanup never silently changes models or providers**: a missing key for its configured provider produces an error. Prefer explicit model prefixes to avoid ambiguous routing.

## Configuration

Copy `.env.example` to `.env` and edit your copy. The `.env` beside `config.py` is loaded at app startup. Priority is:

1. Explicit process environment variables
2. Local `.env` values
3. Python code defaults

The `.env` file is ignored by Git. Changing it requires restarting the app. Do not commit API keys.

| Setting | Code default | Effect |
| --- | --- | --- |
| `PROCESSING_MODE` | `dual` | `dual` = transcription + cleanup; `mono` = one audio model |
| `TRANSCRIPTION_MODEL` | `openai:gpt-transcribe` | Dual-mode speech-to-text model |
| `CLEANUP_MODEL` | `openai/gpt-oss-20b` | Separate cleanup model, routed to Groq by default |
| `MONO_MODEL` | `openai:gpt-audio-mini` | OpenAI or Gemini model for mono mode |
| `OPENAI_API_KEY` | empty | Required for selected OpenAI models |
| `GROQ_API_KEY` | empty | Required for selected Groq models |
| `GEMINI_API_KEY` | empty | Required for selected Gemini models |
| `PRIMARY_PROVIDER` | `groq` | Provider for legacy unprefixed dual-mode model IDs |
| `LANGUAGES` | `Portuguese,English` | Speech language hints and cleanup languages |
| `HOTKEY` | `alt+\` | One global key combination |
| `SILENCE_THRESHOLD` | `1` | WebRTC VAD aggressiveness: 0–3 (larger = more aggressive) |
| `SILENCE_DURATION` | `2.0` | Seconds of silence before flushing a chunk |
| `MIN_CHUNK_DURATION` | `3.0` | Minimum chunk duration in seconds |
| `MONO_PASTE_THRESHOLD` | `0.90` | Score at which mono marks a buffered thought complete |
| `MONO_CONTEXT_CHARS` | `500` | Maximum characters of unfinished context sent to the next mono chunk |
| `MONO_TEMPERATURE` | `0.0` | Sampling temperature for mono processing |
| `MONO_LOG_SCORES` | `false` | Log scores and buffering decisions |
| `CLEANUP_SYSTEM_PROMPT` | built-in cleanup rules | Optional **additional** style preferences; mandatory transcript-only rules remain |
| `OPENAI_TRANSCRIPTION_MODEL` | `whisper-1` | Legacy OpenAI transcription selection/fallback for unprefixed models |
| `OPENAI_CLEANUP_MODEL` | `gpt-4o-mini` | Legacy compatibility value; current pipeline does **not** use it to replace cleanup model |

For `gpt-transcribe`, known language names in `LANGUAGES` map to multiple language hints (e.g. `Portuguese,English` → `pt,en`). Other transcription models receive a single hint only if one language is configured. Unknown language names do not map to hints. The cleanup model receives the original language list in its prompt.

The built-in cleanup policy is kept even when `CLEANUP_SYSTEM_PROMPT` is provided. Use that value only for compatible style preferences, not to replace the application's transcript-only rules.

## Providers and privacy

Dual mode can use OpenAI, Groq, or Gemini for transcription and cleanup if the model supports the request. OpenAI transcription uses the Audio Transcriptions API; cleanup uses each provider's text generation API. Mono uses an audio-capable model plus a structured response with `text` and `completion_score`.

Audio goes to the transcription provider in dual mode; the resulting transcript goes to the cleanup provider. In mono mode, audio and optional preceding text context go to the selected mono provider. Consult each provider's policies before dictating confidential information.

## Troubleshooting

- **Startup fails:** open `not-wisprflow.log` or run `.\.venv\Scripts\python.exe main.py`. Check the required provider keys and model names.
- **Hotkey fails:** check `HOTKEY` and other applications using that shortcut. Global keyboard hooks may behave differently in elevated applications.
- **No microphone audio:** verify the Windows default input and microphone permissions.
- **Text goes into the wrong app:** leave the intended field focused **when processing finishes**. The app intentionally does not lock focus at recording start.
- **An older `.env` uses Whisper:** `TRANSCRIPTION_MODEL=whisper-large-v3-turbo` overrides the code default. Change it to `openai:gpt-transcribe` if that is the desired model.

## Tests and CI

Run tests locally in the project environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/
```

CI runs on **Windows / Python 3.13** for pull requests changing Python code, tests, dependencies, `start.bat`, or the workflow. Documentation-only pull requests skip CI. Merging an already-tested PR or pushing directly to `main` does not trigger another automatic run; use **Actions → CI → Run workflow** to run it manually.

The tests mock provider responses and include a disposable Windows batch-launch smoke test. They do **not** call paid APIs, read your private `.env`, or prove the hotkey works interactively in every Windows application.
