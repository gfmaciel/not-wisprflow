from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from config import Config
from hotkey import GlobalHotkey
from pipeline import Pipeline
from single_instance import SingleInstance
from ui import StatusBar


def main() -> None:
    instance = SingleInstance()
    if not instance.acquire():
        print("[not-wisprflow] Already running; skipping duplicate instance.")
        return

    try:
        config = Config.from_env()
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        bar = StatusBar()
        pipeline = Pipeline(
            config,
            on_state=lambda state: bar.signals.state_changed.emit(state),
            on_spectrum=lambda bands: bar.signals.spectrum.emit(tuple(bands)),
        )
        listener = GlobalHotkey(
            config.hotkey,
            pipeline.on_hotkey_press,
            pipeline.on_hotkey_release,
        )
        try:
            listener.start()
            print(f"[not-wisprflow] Running. Hotkey: {config.hotkey}")
            exit_code = app.exec()
        finally:
            listener.stop()
            pipeline.shutdown()
        if exit_code:
            raise SystemExit(exit_code)
    finally:
        instance.close()


if __name__ == "__main__":
    main()
