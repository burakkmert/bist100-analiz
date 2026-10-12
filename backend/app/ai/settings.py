"""backend/.env dosyasını ortam değişkenlerine yükler (python-dotenv gerektirmeden).

Sunucu (dev_server) ve komut satırı araçları (explain_job, eval.compare) başlarken çağırır.
Zaten tanımlı ortam değişkenlerinin üzerine yazmaz.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()  # satır sonu yorumu
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
