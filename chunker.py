from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass
from typing import Optional

import webrtcvad

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_DURATION_MS = 30
FRAME_SIZE = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples
FRAME_BYTES = FRAME_SIZE * SAMPLE_WIDTH               # 960 bytes


@dataclass(frozen=True)
class AudioChunk:
    wav_bytes: bytes
    # True only when this chunk starts with audio already included in the
    # immediately preceding chunk, as a result of a forced duration split.
    overlaps_previous: bool = False


class Chunker:
    """Use VAD pauses for splits; cap continuous speech with overlapping windows.

    A short utterance is retained until more speech arrives (or recording stops).
    Idle silence is bounded so a long pause cannot grow the recording buffer.
    Only forced splits preserve an audio tail for the next chunk.
    """

    def __init__(
        self,
        aggressiveness: int = 1,
        silence_duration: float = 0.7,
        min_duration: float = 3.0,
        max_duration: float = 12.0,
        overlap_duration: float = 0.8,
    ) -> None:
        if silence_duration <= 0 or min_duration <= 0 or max_duration <= 0:
            raise ValueError("Chunk durations must be positive")
        if max_duration < min_duration:
            raise ValueError("Maximum chunk duration must be >= minimum duration")
        if not 0 <= overlap_duration < max_duration:
            raise ValueError("Overlap duration must be >= 0 and shorter than maximum duration")

        self.vad = webrtcvad.Vad(aggressiveness)
        self._silence_limit = math.ceil(silence_duration * 1000 / FRAME_DURATION_MS)
        self._min_frames = math.ceil(min_duration * 1000 / FRAME_DURATION_MS)
        self._max_frames = math.ceil(max_duration * 1000 / FRAME_DURATION_MS)
        self._overlap_frames = round(overlap_duration * 1000 / FRAME_DURATION_MS)
        self._buffer: list[tuple[bytes, bool]] = []
        self._silence_count = 0
        self._has_new_speech = False
        self._overlaps_previous = False

    def push(self, frame: bytes) -> Optional[AudioChunk]:
        """Feed one 30 ms PCM frame; return a WAV segment when ready."""
        speech = self.vad.is_speech(frame, SAMPLE_RATE)
        self._buffer.append((frame, speech))
        if speech:
            self._has_new_speech = True
            self._silence_count = 0
        else:
            self._silence_count += 1
            if self._overlaps_previous and not self._has_new_speech:
                # A forced split followed only by silence must not resend its
                # overlapping audio as a separate, duplicate transcription.
                if self._silence_count >= self._silence_limit:
                    self._reset()
                    return None
            if self._silence_count > self._silence_limit:
                # Keep only bounded trailing quiet while waiting for a new
                # phrase or retaining an utterance below MIN_CHUNK_DURATION.
                del self._buffer[-(self._silence_limit + 1)]
                self._silence_count = self._silence_limit

        if not self._has_new_speech:
            # Before the first spoken frame, keep only a little pre-roll.
            if not self._overlaps_previous and len(self._buffer) > self._silence_limit:
                del self._buffer[:len(self._buffer) - self._silence_limit]
            return None

        if self._silence_count >= self._silence_limit:
            # After a forced split, always flush the new tail after a pause,
            # even if its *fresh* part is shorter than MIN_CHUNK_DURATION.
            if len(self._buffer) >= self._min_frames or self._overlaps_previous:
                return self._emit(forced=False)
        if len(self._buffer) >= self._max_frames:
            return self._emit(forced=True)
        return None

    def flush_remaining(self) -> Optional[AudioChunk]:
        """Finish the take, without re-emitting an overlap-only tail."""
        if not self._has_new_speech:
            self._reset()
            return None
        return self._emit(forced=False)

    def _emit(self, *, forced: bool) -> AudioChunk:
        # Strip leading silence; preserve the full trailing silence so the
        # recognizer can finish the last word at a natural pause.
        start = next(i for i, (_, speech) in enumerate(self._buffer) if speech)
        frames = self._buffer[start:]
        chunk = AudioChunk(
            wav_bytes=_to_wav([frame for frame, _ in frames]),
            overlaps_previous=self._overlaps_previous,
        )
        if forced and self._overlap_frames:
            self._buffer = frames[-self._overlap_frames:]
            self._overlaps_previous = True
            self._has_new_speech = False
            self._silence_count = 0
            for _, speech in reversed(self._buffer):
                if speech:
                    break
                self._silence_count += 1
        else:
            self._reset()
        return chunk

    def _reset(self) -> None:
        self._buffer.clear()
        self._silence_count = 0
        self._has_new_speech = False
        self._overlaps_previous = False


def _to_wav(frames: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()
