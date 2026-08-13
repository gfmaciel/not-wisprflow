from mono_processor import MonoProcessor
from providers import MonoResult


class FakeProvider:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def process_audio(self, wav_bytes, model, prompt, previous_context="", temperature=0.0):
        self.calls.append({
            "wav_bytes": wav_bytes,
            "model": model,
            "prompt": prompt,
            "previous_context": previous_context,
            "temperature": temperature,
        })
        return next(self.results)


def test_high_score_pastes_immediately():
    pasted = []
    provider = FakeProvider([MonoResult("Complete thought.", 0.96)])
    p = MonoProcessor(provider, "model", "prompt", pasted.append, paste_threshold=0.90)

    p.process(b"wav")

    assert pasted == ["Complete thought. "]
    assert p.pending_text == ""


def test_low_score_becomes_context_for_next_chunk():
    pasted = []
    provider = FakeProvider([
        MonoResult("The main issue is", 0.20),
        MonoResult("the lack of planning.", 0.97),
    ])
    p = MonoProcessor(provider, "model", "prompt", pasted.append, paste_threshold=0.90)

    p.process(b"one")
    assert pasted == []
    assert p.pending_text == "The main issue is"

    p.process(b"two")
    assert provider.calls[1]["previous_context"] == "The main issue is"
    assert pasted == ["The main issue is the lack of planning. "]
    assert p.pending_text == ""


def test_context_is_truncated_but_pending_text_is_not():
    pasted = []
    provider = FakeProvider([
        MonoResult("abcdefghij", 0.1),
        MonoResult("klmnop", 0.1),
    ])
    p = MonoProcessor(provider, "model", "prompt", pasted.append, context_chars=5)

    p.process(b"one")
    p.process(b"two")

    assert provider.calls[1]["previous_context"] == "fghij"
    assert p.pending_text == "abcdefghij klmnop"


def test_flush_pastes_low_confidence_remainder():
    pasted = []
    provider = FakeProvider([MonoResult("unfinished but useful", 0.2)])
    p = MonoProcessor(provider, "model", "prompt", pasted.append)

    p.process(b"wav")
    flushed = p.flush()

    assert flushed == "unfinished but useful"
    assert pasted == ["unfinished but useful "]
    assert p.pending_text == ""


def test_temperature_is_forwarded():
    provider = FakeProvider([MonoResult("Done.", 1.0)])
    p = MonoProcessor(provider, "model", "prompt", lambda _: None, temperature=0.15)
    p.process(b"wav")
    assert provider.calls[0]["temperature"] == 0.15
