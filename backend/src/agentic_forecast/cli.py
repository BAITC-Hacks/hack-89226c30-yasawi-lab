from __future__ import annotations

import argparse
import json

from .agents import run_first_origin
from .config import default_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the approved first-origin backend milestone")
    parser.add_argument("--first-origin", action="store_true", required=True)
    args = parser.parse_args()
    result = run_first_origin(default_settings())
    print(json.dumps({"run_id": result["run_id"], "status": result["status"],
                      "forecast_rows": len(result["forecasts"]), "errors": result["errors"]}, indent=2))


if __name__ == "__main__":
    main()
