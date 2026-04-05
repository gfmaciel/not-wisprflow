from __future__ import annotations
import io
import wave
import webrtcvad
from typing import Optional

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_DURATION_MS = 30
FRAME_SIZE = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples
FRAME_BYTES = FRAME_SIZE * SAMPLE_WIDTH               # 960 bytes


class Chunker:
    """Buffers PCM frames, detects silence via webrtcvad, emits WAV chunks."""

    def __init__(self, aggressiveness: int = 1, silence_duration: float = 2.0, min_duration: float = 3.0):
        self.vad = webrtcvad.Vad(aggressiveness)
        self._silence_limit = int(silence_duration * 1000 / FRAME_DURATION_MS)
        self._min_frames = int(min_duration * 1000 / FRAME_DURATION_MS)
        self._buf: list[tuple[bytes, bool]] = []
        self._held: list[tuple[bytes, bool]] = []
        self._silence_count = 0

    def push(self, frame: bytes) -> Optional[bytes]:
        """Feed a 30ms PCM frame. Returns WAV bytes when a chunk is ready."""
        is_speech = self.vad.is_speech(frame, SAMPLE_RATE)
        self._buf.append((frame, is_speech))
        self._silence_count = 0 if is_speech else self._silence_count + 1
        if self._silence_count >= self._silence_limit:
            return self._flush()
        return None

    def flush_remaining(self) -> Optional[bytes]:
        """Force-emit buffered frames; called when recording stops."""
        return self._flush(force=True)

    def _flush(self, force: bool = False) -> Optional[bytes]:
        has_speech = any(s for _, s in self._buf) or any(s for _, s in self._held)
        if not has_speech:
            self._buf.clear()
            self._silence_count = 0
            return None

        if len(self._buf) < self._min_frames and not force:
            self._held.extend(self._buf)
            self._buf.clear()
            self._silence_count = 0
            return None

        combined = self._held + self._buf
        self._held.clear()
        self._buf.clear()
        self._silence_count = 0

        # Strip leading silence
        start = next((i for i, (_, s) in enumerate(combined) if s), 0)
        frames = [f for f, _ in combined[start:]]
        return _to_wav(frames)


def _to_wav(frames: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()
