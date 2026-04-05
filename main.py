from __future__ import annotations
import sys
import time
import keyboard
from PySide6.QtWidgets import QApplication
from config import Config
from pipeline import Pipeline
from ui import StatusBar


def main() -> None:
    config = Config.from_env()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    bar = StatusBar()

    pipeline = Pipeline(
        config,
        on_state=lambda s: bar.signals.state_changed.emit(s),
        on_amplitude=lambda a: bar.signals.amplitude.emit(a),
    )

    _press_time: list[float] = [0.0]

    def on_press(_event=None) -> None:
        _press_time[0] = time.monotonic()
        pipeline.on_hotkey_press()

    def on_release(_event=None) -> None:
        pipeline.on_hotkey_release(time.monotonic() - _press_time[0])

    # keyboard.add_hotkey handles modifier combos on press;
    # on_release_key fires when the trigger key is lifted.
    try:
        trigger = config.hotkey.split("+")[-1]
        keyboard.add_hotkey(config.hotkey, on_press, suppress=True)
        keyboard.on_release_key(trigger, on_release)
    except ValueError as exc:
        print(f"[not-wisprflow] Invalid HOTKEY '{config.hotkey}': {exc}")
        print("  Fix HOTKEY in your .env — examples: ctrl+shift+space, alt+s, ctrl+f1")
        sys.exit(1)

    print(f"[not-wisprflow] Running. Hotkey: {config.hotkey}  (Ctrl+C to quit)")

    # Start Qt main event loop (PySide6 — not a shell command)
    run_loop = getattr(app, "exec")
    exit_code = run_loop()

    pipeline.shutdown()
    keyboard.unhook_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
