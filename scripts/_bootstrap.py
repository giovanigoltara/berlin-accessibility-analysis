import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent / "src"))

# Python randomises string hashing per process, which changes the iteration
# order of sets of OSM ids. cityseer's network cleaning depends on that order,
# so two runs on identical input gave slightly different segment maps
# (docs/validation.md §8). Fix the seed: when a script is run directly, restart
# it once with PYTHONHASHSEED=0. Imports (e.g. from tests) are left alone.
_main = getattr(sys.modules.get("__main__"), "__file__", None)
if os.environ.get("PYTHONHASHSEED") != "0" and _main and Path(_main).resolve().parent == SCRIPTS:
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])
