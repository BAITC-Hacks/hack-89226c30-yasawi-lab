from __future__ import annotations

import argparse
import json

from .agents import run_first_origin, run_replay
from .config import default_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a wind forecast origin or the approved February replay")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--first-origin", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    result = run_replay(default_settings()) if args.replay else run_first_origin(default_settings())
    print(json.dumps({"run_id": result["run_id"], "status": result["status"],
                      "forecast_rows": len(result["forecasts"]), "progress": result["progress"],
                      "summary": result.get("summary"), "errors": result["errors"]}, indent=2))


if __name__ == "__main__":
    main()
