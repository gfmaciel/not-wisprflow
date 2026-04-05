import io
import wave
from chunker import Chunker, FRAME_BYTES, SAMPLE_RATE, FRAME_DURATION_MS


def _frame():
    return b"\x00" * FRAME_BYTES


def _chunker(seq, silence_s=0.06, min_s=0.09):
    c = Chunker(aggressiveness=1, silence_duration=silence_s, min_duration=min_s)
    it = iter(seq)
    c.vad.is_speech = lambda f, r: next(it)
    return c


def test_chunk_emitted_after_silence():
    n = int(0.06 * 1000 / FRAME_DURATION_MS)
    c = _chunker([True, True, True] + [False] * n)
    result = None
    for _ in range(3 + n):
        result = c.push(_frame())
    assert result is not None


def test_short_chunk_held_not_emitted():
    # silence_s=0.06 -> 2 silence frames; min_s=0.12 -> 4 min frames
    # 1 speech + 2 silence = 3 frames < 4 minimum -> should be held
    n = int(0.06 * 1000 / FRAME_DURATION_MS)
    c = _chunker([True] + [False] * n, min_s=0.12)
    result = None
    for _ in range(1 + n):
        result = c.push(_frame())
    assert result is None


def test_force_flush_emits_held():
    n = int(0.06 * 1000 / FRAME_DURATION_MS)
    c = _chunker([True] + [False] * n, min_s=0.12)
    for _ in range(1 + n):
        c.push(_frame())
    assert c.flush_remaining() is not None


def test_silence_only_emits_nothing():
    n = int(0.06 * 1000 / FRAME_DURATION_MS)
    c = _chunker([False] * n)
    result = None
    for _ in range(n):
        result = c.push(_frame())
    assert result is None


def test_wav_format():
    n = int(0.06 * 1000 / FRAME_DURATION_MS)
    c = _chunker([True, True, True] + [False] * n)
    result = None
    for _ in range(3 + n):
        result = c.push(_frame())
    with wave.open(io.BytesIO(result)) as wf:
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
