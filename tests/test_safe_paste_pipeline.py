from __future__ import annotations

import threading
from unittest.mock import Mock, patch

import pytest

from pipeline import Pipeline


def bare_pipeline() -> Pipeline:
    pipeline = Pipeline.__new__(Pipeline)
    pipeline._processing = False
    pipeline._active = False
    pipeline._tap_mode_on = False
    pipeline._safe_paste_target = True
    pipeline._mode = "dual"
    pipeline._on_spectrum = lambda _: None
    pipeline._futures = []
    pipeline._lock = threading.Lock()
    pipeline._recorder = Mock()
    pipeline._chunker = Mock()
    pipeline._on_state = Mock()
    return pipeline


def test_start_captures_target_before_recording_state_callback():
    pipeline = bare_pipeline()
    order: list[str] = []
    pipeline._on_state = lambda state: order.append(f"state:{state}")
    pipeline._recorder.start.side_effect = lambda callback: order.append("recorder:start")

    with patch("pipeline.start_paste_session", side_effect=lambda **_: order.append("paste:begin")):
        pipeline._start_recording()

    assert order == ["paste:begin", "state:recording", "recorder:start"]
    assert pipeline._active is True


def test_start_passes_rollout_flag_to_paste_session():
    pipeline = bare_pipeline()
    pipeline._safe_paste_target = False

    with patch("pipeline.start_paste_session") as start:
        pipeline._start_recording()

    start.assert_called_once_with(enabled=False)


def test_recorder_start_failure_finishes_paste_session_and_clears_active():
    pipeline = bare_pipeline()
    pipeline._recorder.start.side_effect = RuntimeError("microphone unavailable")

    with (
        patch("pipeline.start_paste_session") as start,
        patch("pipeline.finish_paste_session") as finish,
        pytest.raises(RuntimeError, match="microphone unavailable"),
    ):
        pipeline._start_recording()

    start.assert_called_once_with(enabled=True)
    finish.assert_called_once_with()
    assert pipeline._active is False


def test_collect_with_no_futures_still_finishes_safe_paste_session():
    pipeline = bare_pipeline()
    pipeline._processing = True

    with patch("pipeline.finish_paste_session") as finish:
        pipeline._collect_and_paste()

    finish.assert_called_once_with()
    assert pipeline._processing is False
    pipeline._on_state.assert_called_once_with("idle")
