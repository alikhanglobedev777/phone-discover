"""Start the Phone Discover Django backend with `py dev.py` or `python dev.py`.

Run this file from the repository root. No npm is required.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "backend" / "dev.py"),
        run_name="__main__",
    )
