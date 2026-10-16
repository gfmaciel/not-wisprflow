"""Static plus Windows-only launcher smoke test; no personal configuration read."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_launcher_is_manual_and_uses_windowless_python():
    source = (ROOT / "start.bat").read_text(encoding="utf-8").lower()
    assert "pythonw.exe" in source
    assert "launcher.py" in source
    assert "start " in source
    assert "schtasks" not in source
    assert "reg add" not in source
    assert "startup" not in source


@pytest.mark.skipif(sys.platform != "win32", reason="Batch launch requires Windows")
def test_double_click_batch_launches_pythonw_process(tmp_path):
    """CI smoke: a disposable main.py writes a marker; no actual API calls."""
    for filename in ("start.bat", "launcher.py"):
        shutil.copyfile(ROOT / filename, tmp_path / filename)
    marker = tmp_path / "started.txt"
    (tmp_path / "main.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["cmd.exe", "/c", str(tmp_path / "start.bat")],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    deadline = time.monotonic() + 15
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert marker.read_text() == "started"
