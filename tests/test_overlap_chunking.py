"""Synthetic VAD tests for bounded, overlapping audio chunks."""

import io
import wave

from chunker import Chunker, FRAME_BYTES, SAMPLE_RATE


def _frame(i=0):
    return bytes([i % 256]) * FRAME_BYTES


def _chunker(seq, *, overlap=0.09, minimum=0.09):
    c = Chunker(silence_duration=0.06, min_duration=minimum,
                max_duration=0.3, overlap_duration=overlap)
    it = iter(seq)
    c.vad.is_speech = lambda frame, sample_rate: next(it)
    return c


def _frames(chunk):
    with wave.open(io.BytesIO(chunk.wav_bytes)) as wav:
        assert wav.getframerate() == SAMPLE_RATE
        raw = wav.readframes(wav.getnframes())
    return [raw[i:i + FRAME_BYTES] for i in range(0, len(raw), FRAME_BYTES)]


def test_forced_split_reuses_exact_audio_tail():
    c = _chunker([True] * 17)
    chunks = [c.push(_frame(i)) for i in range(17)]
    first, second = chunks[9], chunks[16]
    assert not first.overlaps_previous
    assert second.overlaps_previous
    assert len(_frames(first)) == len(_frames(second)) == 10
    assert _frames(first)[-3:] == _frames(second)[:3]


def test_natural_pause_is_nonoverlapping():
    c = _chunker([True] * 3 + [False] * 2 +
                 [True] * 3 + [False] * 2)
    emitted = [x for i in range(10) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 2
    assert all(not x.overlaps_previous for x in emitted)


def test_short_tail_after_forced_split_flushes_at_pause():
    c = _chunker([True] * 11 + [False] * 2)
    emitted = [x for i in range(13) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 2
    assert emitted[1].overlaps_previous
    assert len(_frames(emitted[1])) == 6  # 3 shared + 1 fresh + 2 silence


def test_overlap_only_tail_is_not_resent_on_stop():
    c = _chunker([True] * 10)
    emitted = [x for i in range(10) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 1
    assert c.flush_remaining() is None


def test_silence_after_forced_split_drops_overlap_only_tail():
    c = _chunker([True] * 10 + [False] * 2 +
                 [True] * 3 + [False] * 2)
    emitted = [x for i in range(17) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 2
    assert not emitted[1].overlaps_previous


def test_mono_no_overlap_even_at_maximum_duration():
    c = _chunker([True] * 20, overlap=0)
    emitted = [x for i in range(20) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 2
    assert all(not x.overlaps_previous for x in emitted)


def test_short_phrase_waits_for_next_speech_without_growing_with_idle_silence():
    c = _chunker([True] + [False] * 100 + [True] * 3 + [False] * 2,
                 minimum=0.12)
    emitted = [x for i in range(106) if (x := c.push(_frame(i))) is not None]
    assert len(emitted) == 1
    assert not emitted[0].overlaps_previous
    assert len(_frames(emitted[0])) <= 8


def test_long_silence_is_bounded():
    c = _chunker([False] * 500)
    for i in range(500):
        assert c.push(_frame(i)) is None
    assert len(c._buffer) <= 2
    assert c.flush_remaining() is None
