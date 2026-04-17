from __future__ import annotations
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, Optional, Sequence

from groq import Groq
from openai import OpenAI

from config import Config
from recorder import Recorder
from audio_analysis import analyze_mic_frame
from chunker import Chunker
from transcriber import Transcriber
from cleanup import CleanupProcessor
from paste_text import paste

_SPURIOUS_TRANSCRIPTS = {
    "thank you",
    "thanks",
    "thank you.",
    "thank you very much",
    "ok",
    "okay",
}


class Pipeline:
    """
    Orchestrates the full record -> chunk -> transcribe -> cleanup -> paste flow.
    Thread-safe. Notifies UI via on_state(str) and on_amplitude(float) callbacks.
    """

    def __init__(
        self,
        config: Config,
        on_state: Optional[Callable[[str], None]] = None,
        on_spectrum: Optional[Callable[[Sequence[float]], None]] = None,
    ) -> None:
        self._on_state = on_state or (lambda _: None)
        self._on_spectrum = on_spectrum or (lambda _: None)

        # Build available clients
        groq_client = Groq(api_key=config.groq_api_key) if config.groq_api_key else None
        openai_client = OpenAI(api_key=config.openai_api_key) if config.openai_api_key else None

        # Assign primary and fallback based on configured provider
        if config.primary_provider == "openai":
            primary_client = openai_client
            primary_trans_model = config.openai_transcription_model
            primary_cleanup_model = config.openai_cleanup_model
            fallback_client = groq_client
            fallback_trans_model = config.transcription_model
            fallback_cleanup_model = config.cleanup_model
        else:  # groq (default)
            primary_client = groq_client
            primary_trans_model = config.transcription_model
            primary_cleanup_model = config.cleanup_model
            fallback_client = openai_client
            fallback_trans_model = config.openai_transcription_model
            fallback_cleanup_model = config.openai_cleanup_model

        self._recorder = Recorder()
        self._chunker = Chunker(
            aggressiveness=config.silence_aggressiveness,
            silence_duration=config.silence_duration,
            min_duration=config.min_chunk_duration,
        )
        self._transcriber = Transcriber(
            primary_client,
            primary_trans_model,
            config.whisper_language,
            fallback_client=fallback_client,
            fallback_model=fallback_trans_model if fallback_client else None,
        )
        self._cleanup = CleanupProcessor(
            primary_client,
            primary_cleanup_model,
            config.languages,
            config.cleanup_prompt,
            fallback_client=fallback_client,
            fallback_model=fallback_cleanup_model if fallback_client else None,
        )
        self._executor = ThreadPoolExecutor(max_workers=4)

        self._futures: list[Future] = []
        self._lock = threading.Lock()
        self._active = False
        self._tap_mode_on = False

    # ── public hotkey API ────────────────────────────────────────────────────

    def on_hotkey_press(self) -> None:
        """Called on hotkey press. Tap: toggles start/stop. Hold: starts."""
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

    # ── internal ─────────────────────────────────────────────────────────────

    def _start_recording(self) -> None:
        self._active = True
        self._on_state("recording")
        self._recorder.start(self._handle_frame)

    def _stop_recording(self) -> None:
        if not self._active:
            return
        self._active = False
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
        future = self._executor.submit(self._transcriber.transcribe, wav_bytes)
        with self._lock:
            self._futures.append(future)

    def _collect_and_paste(self) -> None:
        try:
            with self._lock:
                futures, self._futures = list(self._futures), []

            if not futures:
                self._on_state("idle")
                return

            future_to_index = {future: idx for idx, future in enumerate(futures)}
            completed: dict[int, str] = {}
            next_index = 0
            transcripts: list[str] = []

            for future in as_completed(futures):
                idx = future_to_index[future]
                try:
                    completed[idx] = future.result()
                except Exception:
                    completed[idx] = ""

                while next_index in completed:
                    transcript = completed.pop(next_index)
                    next_index += 1
                    if self._should_skip_text(transcript):
                        continue
                    transcripts.append(transcript.strip())

            merged = " ".join(part for part in transcripts if part)
            if merged:
                result = self._cleanup.process(merged)
                final = self._cleanup.flush()
                output = result or final
                if output and not self._should_skip_text(output):
                    paste(output)
        except Exception as exc:
            print(f"[not-wisprflow] Error during transcription/paste: {exc}")
        finally:
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
