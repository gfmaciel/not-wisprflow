from concurrent.futures import Future
import threading
from unittest.mock import Mock, patch

from pipeline import Pipeline


def _pipeline(mode="dual"):
    obj = Pipeline.__new__(Pipeline)
    obj._mode = mode
    obj._active = False
    obj._processing = True
    obj._tap_mode_on = False
    obj._recorder = Mock()
    obj._chunker = Mock()
    obj._on_state = Mock()
    obj._futures = []
    obj._lock = threading.Lock()
    obj._on_spectrum = lambda _: None
    obj._mono_paste_buffer = []
    obj._cleanup = Mock()
    obj._cleanup.stream.return_value = iter(["Olá", ", mundo!"])
    obj._mono = Mock()
    return obj


def _future(text):
    future = Future()
    future.set_result(text)
    return future


def test_no_target_is_captured_when_recording_starts():
    obj = _pipeline()
    obj._processing = False
    obj._start_recording()
    obj._recorder.start.assert_called_once()
    obj._on_state.assert_called_once_with("recording")
    assert obj._active


def test_dual_cleanup_is_pasted_once_only_after_stream_finishes():
    obj = _pipeline()
    obj._futures = [_future("Olá mundo.")]
    with patch("pipeline.paste") as paste:
        obj._collect_and_paste()
    paste.assert_called_once_with("Olá, mundo!")
    obj._on_state.assert_called_once_with("idle")


def test_failed_stream_does_not_paste_half_result_before_fallback():
    obj = _pipeline()
    obj._futures = [_future("Hello.")]

    def incomplete():
        yield "Half "
        raise RuntimeError("truncated stream")

    obj._cleanup.stream.return_value = incomplete()
    obj._cleanup.process.return_value = "Hello."
    obj._cleanup.flush.return_value = None
    with patch("pipeline.paste") as paste:
        obj._collect_and_paste()
    paste.assert_called_once_with("Hello.")


def test_mono_is_buffered_until_collect_finishes():
    obj = _pipeline("mono")
    obj._buffer_mono_output("First complete. ")
    obj._mono.flush.side_effect = lambda: obj._buffer_mono_output("Last incomplete. ")
    obj._futures = [_future(None)]
    with patch("pipeline.paste") as paste:
        obj._collect_and_paste()
    paste.assert_called_once_with("First complete. Last incomplete. ")
    assert obj._mono_paste_buffer == []


def test_no_futures_returns_to_idle_without_paste():
    obj = _pipeline()
    with patch("pipeline.paste") as paste:
        obj._collect_and_paste()
    paste.assert_not_called()
    obj._on_state.assert_called_once_with("idle")
