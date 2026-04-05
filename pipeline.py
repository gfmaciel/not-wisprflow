from __future__ import annotations
import struct
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from groq import Groq

from config import Config
from recorder import Recorder
from chunker import Chunker
from transcriber import Transcriber
from cleanup import CleanupProcessor
from paste_text import paste
import sounds


class Pipeline:
    """
    Orchestrates the full record -> chunk -> transcribe -> cleanup -> paste flow.
    Thread-safe. Notifies UI via on_state(str) and on_amplitude(float) callbacks.
    """

    def __init__(
        self,
        config: Config,
        on_state: Optional[Callable[[str], None]] = None,
        on_amplitude: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._on_state = on_state or (lambda _: None)
        self._on_amplitude = on_amplitude or (lambda _: None)

        self._groq = Groq(api_key=config.groq_api_key)
        self._recorder = Recorder()
        self._chunker = Chunker(
            aggressiveness=config.silence_aggressiveness,
            silence_duration=config.silence_duration,
            min_duration=config.min_chunk_duration,
        )
        self._transcriber = Transcriber(
            self._groq, config.transcription_model, config.whisper_language
        )
        self._cleanup = CleanupProcessor(self._groq, config.cleanup_model, config.languages)
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
        else:
            self._tap_mode_on = True

    # ── internal ─────────────────────────────────────────────────────────────

    def _start_recording(self) -> None:
        self._active = True
        self._tap_mode_on = False
        sounds.play_start()
        self._on_state("recording")
        self._recorder.start(self._handle_frame)

    def _stop_recording(self) -> None:
        self._active = False
        self._tap_mode_on = False
        self._recorder.stop()
        sounds.play_stop()
        self._on_state("processing")

        remaining = self._chunker.flush_remaining()
        if remaining:
            self._dispatch_chunk(remaining)

        threading.Thread(target=self._collect_and_paste, daemon=True).start()

    def _handle_frame(self, frame: bytes) -> None:
        if len(frame) >= 2:
            sample = abs(struct.unpack_from("<h", frame)[0]) / 32768.0
            self._on_amplitude(sample)

        chunk = self._chunker.push(frame)
        if chunk:
            self._dispatch_chunk(chunk)

    def _dispatch_chunk(self, wav_bytes: bytes) -> None:
        future = self._executor.submit(self._transcriber.transcribe, wav_bytes)
        with self._lock:
            self._futures.append(future)

    def _collect_and_paste(self) -> None:
        with self._lock:
            futures, self._futures = list(self._futures), []

        transcripts: list[str] = []
        for f in futures:
            try:
                transcripts.append(f.result(timeout=30))
            except Exception:
                pass

        if not transcripts:
            self._on_state("idle")
            return

        cleaned: list[str] = []
        for t in transcripts:
            result = self._cleanup.process(t)
            if result:
                cleaned.append(result)

        final = self._cleanup.flush()
        if final:
            cleaned.append(final)

        if cleaned:
            paste(" ".join(cleaned))

        self._on_state("idle")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
        self._recorder.close()
