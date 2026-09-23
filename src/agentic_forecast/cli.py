from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .agents import DataAgent, ForecastAgent, save_run
from .config import default_settings
from .evaluation import backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic wind-farm generation forecaster")
    parser.add_argument("--cutoff", help="Forecast origin, e.g. 2026-01-31 23:00")
    parser.add_argument("--replay-start", help="Sequential replay start date, e.g. 2026-02-01")
    parser.add_argument("--replay-end", help="Sequential replay end date, e.g. 2026-02-28")
    parser.add_argument("--horizon", type=int, choices=(24, 48), default=48)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--backtest-start", help="Run a development backtest from this hourly origin")
    args = parser.parse_args()
    settings = default_settings()
    if args.output_dir:
        settings = settings.__class__(**{**settings.__dict__, "output_dir": args.output_dir})
    settings = settings.__class__(**{**settings.__dict__, "horizon_hours": args.horizon})
    data = DataAgent(settings).load()
    if args.backtest_start:
        metrics = backtest(data, pd.Timestamp(args.backtest_start), args.horizon, settings.ridge_alpha)
        print(metrics)
        return
    agent = ForecastAgent(settings)
    if bool(args.replay_start) != bool(args.replay_end):
        parser.error("--replay-start and --replay-end must be supplied together")
    if args.replay_start:
        run = agent.replay(data, pd.Timestamp(args.replay_start), pd.Timestamp(args.replay_end))
        prefix = "replay_forecast"
    else:
        cutoff = pd.Timestamp(args.cutoff) if args.cutoff else data.hourly.index.max()
        run = agent.run(data, cutoff)
        prefix = "forecast"
    forecast_path, manifest_path = save_run(run, settings.output_dir, prefix=prefix)
    print(f"forecast: {forecast_path}")
    print(f"manifest: {manifest_path}")
    print(run.forecast.head(3).to_string(index=False))


if __name__ == "__main__":
    main()
