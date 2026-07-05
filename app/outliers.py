"""Outlier detection.

Three complementary univariate methods are provided:

* ``zscore``           - classic mean/standard-deviation z-score.
* ``modified_zscore``  - median/MAD based, robust to the outliers themselves.
* ``iqr``              - Tukey fences at ``k * IQR`` beyond the quartiles.

A value flagged by more methods is a more convincing outlier, so the
combined result ranks entities by how extreme and how corroborated they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

METHODS = ("zscore", "modified_zscore", "iqr")


@dataclass
class OutlierResult:
    """Outcome of running outlier detection on one column."""

    frame: pd.DataFrame
    column: str
    methods: list[str] = field(default_factory=list)
    bounds: dict[str, tuple[float, float]] = field(default_factory=dict)


def zscore(series: pd.Series, threshold: float = 3.0) -> pd.DataFrame:
    values = series.astype(float)
    mean = values.mean()
    std = values.std(ddof=0)
    score = (values - mean) / std if std and not np.isnan(std) else pd.Series(0.0, index=values.index)
    return pd.DataFrame(
        {"zscore": score, "zscore_outlier": score.abs() > threshold},
        index=series.index,
    )


def modified_zscore(series: pd.Series, threshold: float = 3.5) -> pd.DataFrame:
    values = series.astype(float)
    median = values.median()
    mad = (values - median).abs().median()
    if mad and not np.isnan(mad):
        score = 0.6745 * (values - median) / mad
    else:
        score = pd.Series(0.0, index=values.index)
    return pd.DataFrame(
        {"modified_zscore": score, "modified_zscore_outlier": score.abs() > threshold},
        index=series.index,
    )


def iqr(series: pd.Series, k: float = 1.5) -> tuple[pd.DataFrame, tuple[float, float]]:
    values = series.astype(float)
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    spread = q3 - q1
    lower = q1 - k * spread
    upper = q3 + k * spread
    outlier = (values < lower) | (values > upper)
    return (
        pd.DataFrame({"iqr_outlier": outlier}, index=series.index),
        (float(lower), float(upper)),
    )


def detect(
    df: pd.DataFrame,
    column: str,
    methods: tuple[str, ...] = METHODS,
    min_denominator: float | None = None,
    denominator_column: str | None = None,
    zscore_threshold: float = 3.0,
    modified_zscore_threshold: float = 3.5,
    iqr_k: float = 1.5,
) -> OutlierResult:
    """Detect outliers in ``column`` across the rows of ``df``.

    ``min_denominator`` optionally filters out low-volume rows (e.g. players
    with very few challenges) before scoring, so ratios computed from tiny
    samples do not dominate the results.
    """
    invalid = [m for m in methods if m not in METHODS]
    if invalid:
        raise ValueError(f"Unknown method(s) {invalid}; choose from {METHODS}")
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not in frame")

    work = df.copy()
    if denominator_column and min_denominator is not None:
        if denominator_column in work.columns:
            work = work[work[denominator_column].astype(float) >= float(min_denominator)]

    work = work[work[column].notna()].copy()
    result = OutlierResult(frame=work, column=column, methods=list(methods))
    if work.empty:
        work["outlier_score"] = []
        work["outlier_method_count"] = []
        work["is_outlier"] = []
        return result

    series = work[column]
    flags = []

    if "zscore" in methods:
        z = zscore(series, zscore_threshold)
        work["zscore"] = z["zscore"]
        work["zscore_outlier"] = z["zscore_outlier"]
        flags.append("zscore_outlier")

    if "modified_zscore" in methods:
        mz = modified_zscore(series, modified_zscore_threshold)
        work["modified_zscore"] = mz["modified_zscore"]
        work["modified_zscore_outlier"] = mz["modified_zscore_outlier"]
        flags.append("modified_zscore_outlier")

    if "iqr" in methods:
        iq, bounds = iqr(series, iqr_k)
        work["iqr_outlier"] = iq["iqr_outlier"]
        result.bounds["iqr"] = bounds
        flags.append("iqr_outlier")

    work["outlier_method_count"] = work[flags].sum(axis=1).astype(int)
    work["is_outlier"] = work["outlier_method_count"] > 0

    # Score for ranking: magnitude of deviation from the median in robust
    # standard-deviation units, combined with corroboration across methods.
    med = series.median()
    mad = (series - med).abs().median()
    if mad and not np.isnan(mad):
        magnitude = (0.6745 * (series - med) / mad).abs()
    else:
        magnitude = pd.Series(0.0, index=series.index)
    work["outlier_score"] = magnitude * (1 + work["outlier_method_count"])

    work = work.sort_values(
        ["is_outlier", "outlier_score"], ascending=[False, False]
    ).reset_index(drop=True)
    result.frame = work
    return result
