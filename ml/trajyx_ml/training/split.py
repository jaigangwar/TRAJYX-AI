"""Deterministic holdout that separates both junctions and future time."""

from __future__ import annotations

import hashlib

import pandas as pd


def segment_time_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Train on earlier windows at train segments; test on later held-out segments."""
    required = {"segment_id", "window_start"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dataset is missing split columns: {', '.join(sorted(missing))}")
    segments = sorted(frame["segment_id"].dropna().astype(str).unique())
    if len(segments) < 5:
        raise ValueError("at least five distinct road segments are required for a segment-held-out evaluation")
    ordered = sorted(segments, key=lambda value: hashlib.sha256(value.encode()).hexdigest())
    holdout_count = max(1, round(len(ordered) * 0.2))
    heldout = set(ordered[:holdout_count])

    timestamps = pd.to_datetime(frame["window_start"], utc=True, errors="coerce").dropna().sort_values()
    if len(timestamps) < 5:
        raise ValueError("at least five valid time windows are required for a time-held-out evaluation")
    cutoff = timestamps.iloc[int(len(timestamps) * 0.8)]
    parsed = pd.to_datetime(frame["window_start"], utc=True, errors="coerce")
    segment_values = frame["segment_id"].astype(str)
    train_mask = (~segment_values.isin(heldout)) & (parsed < cutoff)
    test_mask = segment_values.isin(heldout) & (parsed >= cutoff)
    train = frame.loc[train_mask].copy()
    test = frame.loc[test_mask].copy()
    if len(train) < 10 or len(test) < 10:
        raise ValueError(
            "the segment/time holdout produced fewer than 10 rows in train or test; "
            "collect more labelled windows across more segments and dates"
        )
    if set(train["segment_id"].astype(str)) & set(test["segment_id"].astype(str)):
        raise AssertionError("segment leakage in evaluation split")
    if pd.to_datetime(train["window_start"], utc=True).max() >= pd.to_datetime(test["window_start"], utc=True).min():
        raise AssertionError("time leakage in evaluation split")
    return train, test, cutoff.isoformat()
