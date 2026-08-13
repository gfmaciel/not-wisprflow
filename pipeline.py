from __future__ import annotations
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, Optional, Sequence

from config import Config, parse_model_spec
from recorder import Recorder
from audio_analysis import analyze_mic_frame
from chunker import Chunker
from transcriber import Transcriber
from cleanup import CleanupProcessor
from mono_processor import MonoProcessor
from paste_text import paste, paste_stream
from providers import GeminiProvider, GroqProvider, OpenAIProvider

_SPURIOUS_TRANSCRIPTS = {
    "thank you",
    "thanks",
    "thank you.",
    "thank you very much",
    "ok",
    "okay",
}


def _is_explicit_model(spec: str) -> bool:
    lower = spec.strip().lower()
    return (
        ":" in spec
        or lower.startswith("gemini-")
        or lower.startswith(("gpt-", "o1", "o3", "o4"))
    )


class Pipeline:
    """
    Orchestrates the full record -> chunk -> AI -> paste flow.

    dual: chunks transcribed in parallel -> merged -> cleanup model -> paste
    mono: chunks processed sequentially by one multimodal model; high-confidence
          complete thoughts paste immediately, incomplete text becomes context
          for the next chunk and is force-flushed when recording ends.
    """

    def __init__(
        self,
        config: Config,
        on_state: Optional[Callable[[str], None]] = None,
        on_spectrum: Optional[Callable[[Sequence[float]], None]] = None,
    ) -> None:
        self._on_state = on_state or (lambda _: None)
        self._on_spectrum = on_spectrum or (lambda _: None)
        self._mode = config.processing_mode

        providers = {}
        if config.groq_api_key:
            providers["groq"] = GroqProvider(config.groq_api_key)
        if config.openai_api_key:
            providers["openai"] = OpenAIProvider(config.openai_api_key)
        if config.gemini_api_key:
            providers["gemini"] = GeminiProvider(config.gemini_api_key)
        self._providers = providers

        self._transcriber = None
        self._cleanup = None
        self._mono = None

        if self._mode == "mono":
            provider_name, model = parse_model_spec(config.mono_model)
            self._mono = MonoProcessor(
                providers[provider_name],
                model,
                self._build_mono_prompt(config),
                paste,
                paste_threshold=config.mono_paste_threshold,
                context_chars=config.mono_context_chars,
                temperature=config.mono_temperature,
                should_skip=self._should_skip_text,
                log_scores=config.mono_log_scores,
            )
        else:
            trans = self._resolve_dual_stage(config, "transcription")
            clean = self._resolve_dual_stage(config, "cleanup")
            self._transcriber = Transcriber(
                trans["provider"],
                trans["model"],
                config.whisper_language,
                fallback_provider=trans["fallback_provider"],
                fallback_model=trans["fallback_model"],
            )
            self._cleanup = CleanupProcessor(
                clean["provider"],
                clean["model"],
                config.languages,
                config.cleanup_prompt,
                fallback_provider=clean["fallback_provider"],
                fallback_model=clean["fallback_model"],
            )

        self._recorder = Recorder()
        self._chunker = Chunker(
            aggressiveness=config.silence_aggressiveness,
            silence_duration=config.silence_duration,
            min_duration=config.min_chunk_duration,
        )
        self._executor = ThreadPoolExecutor(max_workers=1 if self._mode == "mono" else 4)

        self._futures: list[Future] = []
        self._lock = threading.Lock()
        self._active = False
        self._processing = False
        self._tap_mode_on = False

        if self._mode == "dual":
            self._executor.submit(self._warmup)

    def _resolve_dual_stage(self, config: Config, stage: str) -> dict:
        if stage == "transcription":
            configured = config.transcription_model
            openai_model = config.openai_transcription_model
            groq_model = config.transcription_model
        else:
            configured = config.cleanup_model
            openai_model = config.openai_cleanup_model
            groq_model = config.cleanup_model

        if _is_explicit_model(configured):
            provider_name, model = parse_model_spec(configured, config.primary_provider)
            return {
                "provider": self._providers[provider_name],
                "model": model,
                "fallback_provider": None,
                "fallback_model": None,
            }

        if config.primary_provider == "openai":
            primary_name, primary_model = "openai", openai_model
            fallback_name, fallback_model = "groq", groq_model
        else:
            primary_name, primary_model = "groq", groq_model
            fallback_name, fallback_model = "openai", openai_model

        fallback_provider = self._providers.get(fallback_name)
        return {
            "provider": self._providers[primary_name],
            "model": primary_model,
            "fallback_provider": fallback_provider,
            "fallback_model": fallback_model if fallback_provider else None,
        }

    @staticmethod
    def _build_mono_prompt(config: Config) -> str:
        prompt = config.cleanup_prompt
        if config.languages:
            prompt += (
                "\nThe user may speak any of the following languages: "
                + ", ".join(config.languages)
                + "."
            )
        prompt += (
            "\n\nMONO MODE OUTPUT CONTRACT (this supersedes any instruction above about "
            "returning only plain text): you are receiving one audio chunk plus, sometimes, "
            "a short text excerpt from an unfinished previous chunk. Transcribe and clean ONLY "
            "the current audio; never repeat the previous context. Also estimate a "
            "completion_score from 0 to 1 for whether the combined unfinished context plus the "
            "current chunk now form a self-contained semantic thought that can safely be pasted "
            "without hearing the next chunk. Give low scores to clearly open syntax or meaning "
            "(for example endings like 'because', 'that', 'and', or an unfinished list), and high "
            "scores only when the thought is genuinely complete. The score is an operational "
            "confidence ranking, not a calibrated probability. Be conservative near ambiguity."
        )
        return prompt

    def _warmup(self) -> None:
        """Best-effort warmup of the dual-mode cleanup provider connection."""
        try:
            self._cleanup._provider.cleanup(
                "ok",
                self._cleanup._model,
                self._cleanup._build_system_prompt(),
            )
        except Exception:
            pass

    def on_hotkey_press(self) -> None:
        """Called on hotkey press. Tap: toggles start/stop. Hold: starts."""
        if self._processing:
            return
        if self._tap_mode_on:
            self._stop_recording()
        else:
            self._start_recording()

    def on_hotkey_release(self, held_duration: float) -> None:
        """
        Called on hotkey release.
        >0.5s held  -> hold mode, stop now.
        <=0.5s held -> tap mode, keep recording until second press.
        """
        if held_duration > 0.5 and self._active:
            self._stop_recording()
        elif self._active:
            self._tap_mode_on = True

    def _start_recording(self) -> None:
        if self._processing:
            return
        if self._mode == "mono":
            self._mono.reset()
        self._active = True
        self._on_state("recording")
        self._recorder.start(self._handle_frame)

    def _stop_recording(self) -> None:
        if not self._active:
            return
        self._active = False
        self._processing = True
        self._tap_mode_on = False
        self._recorder.stop()
        self._on_state("processing")

        remaining = self._chunker.flush_remaining()
        if remaining:
            self._dispatch_chunk(remaining)

        threading.Thread(target=self._collect_and_paste, daemon=True).start()

    def _handle_frame(self, frame: bytes) -> None:
        bands = analyze_mic_frame(frame)
        self._on_spectrum(bands)

        chunk = self._chunker.push(frame)
        if chunk:
            self._dispatch_chunk(chunk)

    def _dispatch_chunk(self, wav_bytes: bytes) -> None:
        if self._mode == "mono":
            future = self._executor.submit(self._mono.process, wav_bytes)
        else:
            future = self._executor.submit(self._transcriber.transcribe, wav_bytes)
        with self._lock:
            self._futures.append(future)

    def _collect_and_paste(self) -> None:
        try:
            with self._lock:
                futures, self._futures = list(self._futures), []

            if not futures:
                return

            if self._mode == "mono":
                for future in futures:
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"[not-wisprflow] Mono AI processing chunk failed: {exc}")
                self._mono.flush()
                return

            future_to_index = {future: idx for idx, future in enumerate(futures)}
            completed: dict[int, str] = {}
            next_index = 0
            outputs: list[str] = []

            for future in as_completed(futures):
                idx = future_to_index[future]
                try:
                    completed[idx] = future.result()
                except Exception:
                    completed[idx] = ""

                while next_index in completed:
                    text = completed.pop(next_index)
                    next_index += 1
                    if self._should_skip_text(text):
                        continue
                    outputs.append(text.strip())

            merged = " ".join(part for part in outputs if part)
            if not merged or self._should_skip_text(merged):
                return

            try:
                typed = paste_stream(self._cleanup.stream(merged))
                if typed:
                    return
            except Exception as exc:
                print(f"[not-wisprflow] Streaming cleanup failed ({exc}); falling back.")

            result = self._cleanup.process(merged)
            final = self._cleanup.flush()
            output = result or final
            if output and not self._should_skip_text(output):
                paste(output)
        except Exception as exc:
            print(f"[not-wisprflow] Error during transcription/paste: {exc}")
        finally:
            self._processing = False
            self._on_state("idle")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
        self._recorder.close()

    @staticmethod
    def _should_skip_text(text: str) -> bool:
        normalized = " ".join(text.lower().split()).strip(" .,!?:;\"'")
        if not normalized:
            return True
        if normalized in _SPURIOUS_TRANSCRIPTS:
            return True
        if len(normalized) <= 2:
            return True
        return False
