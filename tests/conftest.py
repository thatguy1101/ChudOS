import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "applications" / "chudos-welcome"))
sys.path.insert(0, str(ROOT / "applications" / "chudos-profiles"))
sys.path.insert(0, str(ROOT / "applications" / "chudos-monitor"))
sys.path.insert(0, str(ROOT / "applications" / "chudos-store"))
sys.path.insert(0, str(ROOT / "applications" / "chudos-installer"))
sys.path.insert(0, str(ROOT / "applications" / "chudos-control-center"))
sys.path.insert(0, str(ROOT / "tools" / "validation"))
sys.path.insert(0, str(ROOT / "tools" / "build-iso"))
