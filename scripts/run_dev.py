from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn

from app.db import init_db


if __name__ == "__main__":
    init_db()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8010,
        reload=False,
        log_level="critical",
        access_log=False,
        log_config=None,
    )
