from __future__ import annotations
import threading
from typing import Callable
import pyaudio
from chunker import SAMPLE_RATE, FRAME_SIZE, FRAME_BYTES


class Recorder:
    """
    Opens the default microphone and streams 30ms raw PCM frames.
    Call start(on_frame) to begin; on_frame receives each frame as bytes.
    Call stop() to end.
    """

    def __init__(self) -> None:
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, on_frame: Callable[[bytes], None]) -> None:
        self._running = True
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_SIZE,
        )
        self._thread = threading.Thread(target=self._loop, args=(on_frame,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()

    def close(self) -> None:
        self._pa.terminate()

    def _loop(self, on_frame: Callable[[bytes], None]) -> None:
        while self._running:
            try:
                frame = self._stream.read(FRAME_SIZE, exception_on_overflow=False)
                if len(frame) == FRAME_BYTES:
                    on_frame(frame)
            except OSError:
                break
