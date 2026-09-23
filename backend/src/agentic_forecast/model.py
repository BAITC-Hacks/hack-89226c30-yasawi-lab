from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .data import TurbineData


FEATURES = ["wind_speed", "temperature"]
FEATURE_SET_VERSION = "wind-temperature-v1"
PARAMETERS = {"loss": "squared_error", "learning_rate": 0.08, "max_iter": 180,
              "max_leaf_nodes": 31, "l2_regularization": 0.1, "random_state": 42}


def atomic_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(content, target, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass
class ModelResult:
    model: HistGradientBoostingRegressor
    manifest: dict


def fit_or_load(data: TurbineData, origin: datetime, artifacts_dir: Path) -> ModelResult:
    origin_utc = origin.astimezone(timezone.utc)
    frame = data.hourly
    eligible = frame.loc[(frame.index + timedelta(hours=1) <= origin) & frame["is_complete"]].copy()
    eligible = eligible.loc[eligible["source_last_utc"].map(lambda x: x.to_pydatetime() < origin_utc)]
    if len(eligible) < 100:
        raise ValueError(f"{data.turbine_id}: insufficient complete pre-origin hours ({len(eligible)})")
    cutoff = eligible.index.max() + timedelta(hours=1)
    identity = {"turbine_id": data.turbine_id, "training_cutoff": cutoff.isoformat(),
                "dataset_sha256": data.sha256, "feature_set_version": FEATURE_SET_VERSION,
                "sklearn_version": sklearn.__version__, "parameters": PARAMETERS}
    version = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    model_dir = artifacts_dir / "models"
    model_path = model_dir / f"{data.turbine_id}-{version}.joblib"
    manifest_path = model_dir / f"{data.turbine_id}-{version}.json"
    if model_path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("identity") == identity:
            return ModelResult(joblib.load(model_path), manifest)
    holdout_start = origin.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=14)
    development = eligible.loc[eligible.index < holdout_start]
    holdout = eligible.loc[(eligible.index >= holdout_start) & (eligible.index < origin)]
    evaluation = {"status": "unavailable", "scope": "14 pre-origin local calendar days; measured historical wind and temperature",
                  "mae": None, "rmse": None, "reason": "insufficient complete development or holdout hours",
                  "development_rows": len(development), "holdout_rows": len(holdout),
                  "holdout_start": holdout_start.isoformat(), "holdout_end": origin.isoformat(),
                  "measured_historical_weather": True}
    if len(development) >= 100 and len(holdout) >= 24:
        check = HistGradientBoostingRegressor(**PARAMETERS).fit(development[FEATURES], development["power"])
        predicted = check.predict(holdout[FEATURES])
        evaluation.update(status="available", mae=float(mean_absolute_error(holdout["power"], predicted)),
                          rmse=float(math.sqrt(mean_squared_error(holdout["power"], predicted))), reason=None)
    model = HistGradientBoostingRegressor(**PARAMETERS).fit(eligible[FEATURES], eligible["power"])
    manifest = {"model_version": version, "model_class": "sklearn.ensemble.HistGradientBoostingRegressor",
                "identity": identity, "features": FEATURES, "training_rows": len(eligible),
                "first_training_hour": eligible.index.min().isoformat(), "last_training_hour": eligible.index.max().isoformat(),
                "target": "hourly_mean_normalized_active_power", "evaluation": evaluation,
                "model_path": str(model_path), "created_at_utc": datetime.now(timezone.utc).isoformat()}
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=model_dir, suffix=".tmp")
    os.close(fd)
    try:
        joblib.dump(model, name)
        os.replace(name, model_path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    atomic_json(manifest_path, manifest)
    return ModelResult(model, manifest)


def predict(model: HistGradientBoostingRegressor, wind: list[float], temperature: list[float]) -> list[float]:
    values = model.predict(pd.DataFrame({"wind_speed": wind, "temperature": temperature}))
    if len(values) != 48 or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("Forecast output is non-finite, out of [0,1], or not 48 hours")
    return [float(x) for x in values]
