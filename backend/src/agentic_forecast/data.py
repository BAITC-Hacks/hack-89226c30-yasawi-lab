from __future__ import annotations

import csv
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


HEADERS = [
    "ID", "Статистическое время", "Средняя скорость ветра(m/s)",
    "Нормализованная активная мощность", "Средняя температура окружающей среды(°C)",
]
MEASURES = ("wind_speed", "power", "temperature")


class SourceQualityError(ValueError):
    def __init__(self, path: Path, issues: list[dict]):
        self.path, self.issues = path, issues
        super().__init__(f"{path.name}: {len(issues)} source-quality issue(s)")


@dataclass
class TurbineData:
    turbine_id: str
    dataset_id: str
    path: Path
    sha256: str
    raw_row_count: int
    hourly: pd.DataFrame
    quality: dict


def _localize(value: str, zone: ZoneInfo) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}", value):
        raise ValueError("expected YYYY-MM-DD H:MM:SS")
    naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    a, b = naive.replace(tzinfo=zone, fold=0), naive.replace(tzinfo=zone, fold=1)
    if a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        raise ValueError("nonexistent local time")
    if a.utcoffset() != b.utcoffset():
        raise ValueError("ambiguous local time")
    return a


def _measure(value: str, field: str, row_number: int, issues: list[dict]) -> float:
    if value.strip() == "":
        return math.nan
    try:
        result = float(value)
    except ValueError:
        issues.append({"row": row_number, "field": field, "value": value, "reason": "not_numeric"})
        return math.nan
    if not math.isfinite(result):
        issues.append({"row": row_number, "field": field, "value": value, "reason": "non_finite"})
    elif field == "wind_speed" and result < 0:
        issues.append({"row": row_number, "field": field, "value": value, "reason": "negative_wind"})
    elif field == "power" and not 0 <= result <= 1:
        issues.append({"row": row_number, "field": field, "value": value, "reason": "power_out_of_range"})
    return result


def load_turbine(path: Path, turbine_id: str, zone: ZoneInfo) -> TurbineData:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    issues: list[dict] = []
    rejected_local_times: list[dict] = []
    records: list[dict] = []
    seen_times: set[datetime] = set()
    seen_ids: set[int] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != HEADERS:
            raise SourceQualityError(path, [{"row": 1, "field": "header", "expected": HEADERS, "actual": reader.fieldnames}])
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                issues.append({"row": row_number, "field": "row", "reason": "extra_columns"})
                continue
            try:
                record_id = int(row[HEADERS[0]])
                if str(record_id) != row[HEADERS[0]].strip():
                    raise ValueError()
            except (ValueError, TypeError):
                issues.append({"row": row_number, "field": "ID", "value": row[HEADERS[0]], "reason": "invalid_integer"})
                continue
            if record_id in seen_ids:
                issues.append({"row": row_number, "field": "ID", "value": record_id, "reason": "duplicate_id"})
            seen_ids.add(record_id)
            raw_time = row[HEADERS[1]]
            try:
                local = _localize(raw_time, zone)
            except (ValueError, TypeError) as exc:
                detail = {"row": row_number, "field": HEADERS[1], "value": raw_time, "reason": str(exc)}
                if str(exc) in ("nonexistent local time", "ambiguous local time"):
                    rejected_local_times.append(detail)
                else:
                    issues.append(detail)
                continue
            utc = local.astimezone(timezone.utc)
            if utc in seen_times:
                issues.append({"row": row_number, "field": HEADERS[1], "value": raw_time, "reason": "duplicate_timestamp"})
            seen_times.add(utc)
            values = {key: _measure(row[header] or "", key, row_number, issues)
                      for key, header in zip(MEASURES, HEADERS[2:])}
            records.append({"id": record_id, "row_number": row_number, "raw_timestamp": raw_time,
                            "local_time": local, "utc_time": utc, **values})
    if issues:
        raise SourceQualityError(path, issues)
    if not records:
        raise SourceQualityError(path, [{"row": 1, "reason": "empty_dataset"}])
    frame = pd.DataFrame.from_records(records)
    local_index = pd.DatetimeIndex(frame["utc_time"]).tz_convert(zone)
    frame["hour"] = local_index.floor("h")
    frame["slot"] = local_index.minute
    frame["complete_sample"] = frame[list(MEASURES)].notna().all(axis=1)
    frame["valid_slot"] = frame["slot"].isin((0, 10, 20, 30, 40, 50)) & (local_index.second == 0)
    grouped = frame.groupby("hour", sort=True)
    hourly = grouped[list(MEASURES)].mean()
    hourly["raw_sample_count"] = grouped.size()
    hourly["sample_count"] = grouped["complete_sample"].sum().astype(int)
    hourly["distinct_slot_count"] = grouped["slot"].nunique()
    hourly["valid_slot_count"] = grouped["valid_slot"].sum().astype(int)
    hourly["source_first_utc"] = grouped["utc_time"].min()
    hourly["source_last_utc"] = grouped["utc_time"].max()
    full_index = pd.date_range(hourly.index.min(), hourly.index.max(), freq="h", tz=zone, name="hour")
    hourly = hourly.reindex(full_index)
    for column in ("raw_sample_count", "sample_count", "distinct_slot_count", "valid_slot_count"):
        hourly[column] = hourly[column].fillna(0).astype(int)
    missing = hourly["raw_sample_count"] == 0
    complete = (hourly["raw_sample_count"] == 6) & (hourly["sample_count"] == 6) & (hourly["distinct_slot_count"] == 6) & (hourly["valid_slot_count"] == 6)
    hourly["quality_flags"] = [["MISSING_HOUR"] if m else ([] if c else ["INCOMPLETE_HOUR"])
                               for m, c in zip(missing, complete)]
    hourly["is_complete"] = complete
    quality = {"raw_rows": len(records) + len(rejected_local_times), "accepted_rows": len(records),
               "hourly_bins": len(hourly), "occupied_hours": int((~missing).sum()),
               "complete_hours": int(complete.sum()), "incomplete_hours": int((~missing & ~complete).sum()),
               "missing_hours": int(missing.sum()), "first_local": frame["local_time"].min().isoformat(),
               "last_local": frame["local_time"].max().isoformat(),
               "rejected_unlocalizable_rows": len(rejected_local_times),
               "rejected_unlocalizable_examples": rejected_local_times[:10]}
    return TurbineData(turbine_id, path.name, path, digest, len(records) + len(rejected_local_times), hourly, quality)


def load_all(data_dir: Path, zone: ZoneInfo) -> dict[str, TurbineData]:
    return {f"turbine_{i}": load_turbine(data_dir / f"dataset_{i}.csv", f"turbine_{i}", zone)
            for i in (1, 2)}
