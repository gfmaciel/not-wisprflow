import threading
import winsound


def _beep(freq: int, ms: int) -> None:
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()


def play_start() -> None:
    """High click on recording start."""
    _beep(880, 80)


def play_stop() -> None:
    """Lower pop on recording stop."""
    _beep(440, 80)
