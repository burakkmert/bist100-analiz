# `pytest app/ai/tests` backend/ kökünden çalıştırılınca `app` paketi bulunsun diye
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
