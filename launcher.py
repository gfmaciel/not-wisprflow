"""Windows console-free entrypoint; capture startup errors from pythonw."""
from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    with (root / "not-wisprflow.log").open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout, sys.stderr = log, log
        try:
            runpy.run_path(str(root / "main.py"), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (0, None):
                print(f"[not-wisprflow] Exit code: {exc.code}", file=log)
                if isinstance(exc.code, str):
                    print(exc.code, file=log)
        except BaseException:
            traceback.print_exc(file=log)


if __name__ == "__main__":
    main()
