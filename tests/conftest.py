import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
# ui.py imports sibling modules as top-level (`from storage import ...`), so both paths are needed.
for p in (_ROOT, _ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
