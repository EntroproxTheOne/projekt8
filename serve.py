import sys
from pathlib import Path


deps = Path(__file__).parent / ".python_deps"
if deps.exists():
    sys.path.insert(0, str(deps))

import uvicorn  # noqa: E402


if __name__ == "__main__":
    uvicorn.run("video_pipeline.webapp:app", host="127.0.0.1", port=8000)
