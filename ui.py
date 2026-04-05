from __future__ import annotations
from collections import deque
from PySide6.QtWidgets import QMainWindow, QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPainter, QColor, QPen

BAR_HEIGHT = 28
BAR_WIDTH = 360
WAVEFORM_HISTORY = 120
PULSE_TICK_MS = 60


class _Signals(QObject):
    state_changed = Signal(str)
    amplitude = Signal(float)


class _WaveformWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._samples: deque[float] = deque([0.0] * WAVEFORM_HISTORY, maxlen=WAVEFORM_HISTORY)
        self._state = "idle"
        self._pulse = 0.0
        self._pulse_dir = 1

        timer = QTimer(self)
        timer.timeout.connect(self._tick_pulse)
        timer.start(PULSE_TICK_MS)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def add_amplitude(self, value: float) -> None:
        self._samples.append(value)
        self.update()

    def _tick_pulse(self) -> None:
        if self._state == "processing":
            self._pulse += 0.05 * self._pulse_dir
            if self._pulse >= 1.0 or self._pulse <= 0.0:
                self._pulse_dir *= -1
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        bg = QColor("#c0392b") if self._state == "error" else QColor("#1a1a1a")
        p.fillRect(0, 0, w, h, bg)

        if self._state in ("recording", "processing"):
            samples = list(self._samples)
            bar_w = max(3, w // len(samples))
            color = QColor("#00d4aa") if self._state == "recording" else QColor("#00d4aa").darker(150)
            p.setPen(QPen(color, 1))
            mid = h // 2
            for i, amp in enumerate(samples):
                amp_scaled = min(1.0, amp * 6)
                bh = int(amp_scaled * (h - 4))
                p.drawLine(i * bar_w, mid - bh // 2, i * bar_w, mid + bh // 2)

            if self._state == "processing":
                p.fillRect(0, 0, w, h, QColor(0, 212, 170, int(self._pulse * 80)))

        p.end()


class StatusBar(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - BAR_WIDTH) // 2
        self.setGeometry(x, screen.y(), BAR_WIDTH, BAR_HEIGHT)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )

        self._waveform = _WaveformWidget(self)
        self.setCentralWidget(self._waveform)

        self.signals = _Signals()
        self.signals.state_changed.connect(self._on_state)
        self.signals.amplitude.connect(self._waveform.add_amplitude)

        self.hide()

    def _on_state(self, state: str) -> None:
        self._waveform.set_state(state)
        self.hide() if state == "idle" else self.show()

    def set_error(self, message: str) -> None:
        self.signals.state_changed.emit("error")
        self.setToolTip(message)
