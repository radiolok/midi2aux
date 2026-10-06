import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE / "unit", HERE / "system", HERE.parent / "model"):
    sys.path.insert(0, str(p))
