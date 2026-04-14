from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QWidget, QApplication, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QBrush

WINDOW_WIDTH = 224
WINDOW_HEIGHT = 54
PILL_WIDTH = 200
PILL_HEIGHT = 40
PILL_TOP = 6
PILL_RADIUS = PILL_HEIGHT / 2
BAR_COUNT = 9
BAR_SPACING = 9
BAR_WIDTH = 6
BAR_MIN_HEIGHT = 3
BAR_MAX_EXTRA = 31
TICK_MS = 16


class _Signals(QObject):
    state_changed = Signal(str)
    spectrum = Signal(object)


class _WaveformWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self._levels = [0.0] * BAR_COUNT
        self._targets = [0.0] * BAR_COUNT
        self._pulse = 0.0
        self._pulse_dir = 1

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none; margin: 0px; padding: 0px;")

        timer = QTimer(self)
        timer.setInterval(TICK_MS)
        timer.timeout.connect(self._tick)
        timer.start()

    def set_state(self, state: str) -> None:
        self._state = state
        if state == "idle":
            self._targets = [0.0] * BAR_COUNT
            self._levels = [0.0] * BAR_COUNT
            self._pulse = 0.0
        elif state == "processing":
            self._targets = self._levels[:]
            self._pulse = 0.0
            self._pulse_dir = 1
        elif state == "recording":
            self._targets = [0.0] * BAR_COUNT
        self.update()

    def set_spectrum(self, bands: tuple[float, ...] | list[float]) -> None:
        if self._state != "recording":
            return

        normalized = list(bands[:BAR_COUNT]) if len(bands) >= BAR_COUNT else list(bands)
        if len(normalized) < BAR_COUNT:
            normalized.extend([0.0] * (BAR_COUNT - len(normalized)))
        self._targets = [max(0.0, min(1.0, value)) for value in normalized]

    def _tick(self) -> None:
        for idx, target in enumerate(self._targets):
            current = self._levels[idx]
            self._levels[idx] = current + (target - current) * 0.2

        if self._state == "processing":
            self._pulse += 0.04 * self._pulse_dir
            if self._pulse >= 1.0:
                self._pulse = 1.0
                self._pulse_dir = -1
            elif self._pulse <= 0.0:
                self._pulse = 0.0
                self._pulse_dir = 1

        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        if self._state == "idle":
            painter.end()
            return

        w = self.width()
        pill_x = (w - PILL_WIDTH) // 2
        pill_y = PILL_TOP
        pill_rect = QRectF(pill_x, pill_y, PILL_WIDTH, PILL_HEIGHT)

        # Shadow stack to suggest depth without hard edges.
        for offset, alpha, spread in ((5, 20, 7), (3, 36, 4), (1, 60, 2)):
            shadow = QRectF(
                pill_rect.x() - spread / 2,
                pill_rect.y() + offset - spread / 3,
                pill_rect.width() + spread,
                pill_rect.height() + spread,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(shadow, PILL_RADIUS + spread / 2, PILL_RADIUS + spread / 2)

        capsule = QLinearGradient(pill_rect.topLeft(), pill_rect.bottomLeft())
        capsule.setColorAt(0.0, QColor(9, 16, 38, 248))
        capsule.setColorAt(1.0, QColor(6, 12, 28, 248))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(capsule))
        painter.drawRoundedRect(pill_rect, PILL_RADIUS, PILL_RADIUS)

        highlight = QRectF(pill_rect.x() + 2, pill_rect.y() + 2, pill_rect.width() - 4, 1.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(highlight, 0.75, 0.75)

        bands = self._levels
        center_y = pill_rect.center().y()
        total_width = BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_SPACING
        start_x = pill_rect.center().x() - total_width / 2

        for idx, value in enumerate(bands):
            distance = abs(idx - (BAR_COUNT - 1) / 2.0) / ((BAR_COUNT - 1) / 2.0)
            envelope = 0.52 + (1.0 - distance) * 0.48
            height = BAR_MIN_HEIGHT + int(value * BAR_MAX_EXTRA * envelope)
            bar_x = start_x + idx * (BAR_WIDTH + BAR_SPACING)
            bar_y = center_y - height / 2
            if idx == BAR_COUNT // 2:
                color = QColor(236, 255, 248, 250)
            else:
                color = QColor(66, 245, 189, 240)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(bar_x, bar_y, BAR_WIDTH, height), BAR_WIDTH / 2, BAR_WIDTH / 2)

        if self._state == "processing":
            pulse_alpha = int(14 + self._pulse * 28)
            pulse_rect = QRectF(pill_rect.x() + 6, pill_rect.y() + 5, pill_rect.width() - 12, pill_rect.height() - 10)
            painter.setBrush(QColor(66, 245, 189, pulse_alpha))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(pulse_rect, PILL_RADIUS - 5, PILL_RADIUS - 5)

        painter.end()


class StatusBar(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            "background-color: transparent; border: none; outline: none; margin: 0px; padding: 0px;"
        )

        self._root = QWidget(self)
        self._root.setAttribute(Qt.WA_TranslucentBackground, True)
        self._root.setStyleSheet(
            "background-color: transparent; border: none; outline: none; margin: 0px; padding: 0px;"
        )
        self.setCentralWidget(self._root)

        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._waveform = _WaveformWidget(self._root)
        self._waveform.setStyleSheet(
            "background-color: transparent; border: none; outline: none; margin: 0px; padding: 0px;"
        )
        layout.addWidget(self._waveform)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._waveform.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.signals = _Signals()
        self.signals.state_changed.connect(self._on_state)
        self.signals.spectrum.connect(self._waveform.set_spectrum)

        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - WINDOW_WIDTH) // 2
        y = screen.y()
        self.move(x, y)
        self.hide()
        self._remove_dwm_border()

    def _remove_dwm_border(self) -> None:
        try:
            import ctypes

            hwnd = int(self.winId())

            # Windows 11 draws a 1px border around all top-level windows via DWM.
            # DWMWA_BORDER_COLOR (attr 34) with DWMWA_COLOR_NONE suppresses it.
            DWMWA_BORDER_COLOR = 34
            DWMWA_COLOR_NONE = 0xFFFFFFFE
            color = ctypes.c_uint(DWMWA_COLOR_NONE)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR, ctypes.byref(color), ctypes.sizeof(color)
            )
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._remove_dwm_border()

    def _on_state(self, state: str) -> None:
        self._waveform.set_state(state)
        self.hide() if state == "idle" else self.show()

    def set_error(self, message: str) -> None:
        self.signals.state_changed.emit("error")
        self.setToolTip(message)
