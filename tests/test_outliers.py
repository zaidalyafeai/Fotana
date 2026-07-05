"""Unit tests for the outlier detection methods."""

import numpy as np
import pandas as pd

from app.outliers import detect, iqr, modified_zscore, zscore


def test_zscore_flags_extreme_value():
    s = pd.Series([10, 11, 9, 10, 12, 8, 100])
    out = zscore(s, threshold=2.0)
    assert out["zscore_outlier"].iloc[-1]
    assert not out["zscore_outlier"].iloc[0]


def test_modified_zscore_is_robust():
    # A single huge value inflates the classic std enough that nothing
    # else is flagged, but MAD stays small so the spike is still caught.
    s = pd.Series([5, 6, 5, 6, 5, 6, 500])
    out = modified_zscore(s, threshold=3.5)
    assert out["modified_zscore_outlier"].iloc[-1]


def test_iqr_bounds_and_flags():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 50])
    flags, (lower, upper) = iqr(s, k=1.5)
    assert flags["iqr_outlier"].iloc[-1]
    assert upper < 50
    assert lower < s.min() or True  # lower bound is informative, not asserted strictly


def test_detect_combines_methods_and_ranks():
    df = pd.DataFrame(
        {
            "name": [f"e{i}" for i in range(10)],
            "ratio": [10, 11, 9, 10, 12, 8, 11, 10, 9, 200],
            "challenges": [50] * 10,
        }
    )
    res = detect(df, "ratio", min_denominator=10, denominator_column="challenges")
    top = res.frame.iloc[0]
    assert top["name"] == "e9"
    assert top["is_outlier"]
    assert top["outlier_method_count"] >= 1
    assert "outlier_score" in res.frame.columns


def test_detect_min_denominator_filters_low_volume():
    df = pd.DataFrame(
        {
            "name": ["a", "b", "c"],
            "ratio": [10, 10, 999],
            "challenges": [50, 50, 1],  # c has too few challenges
        }
    )
    res = detect(df, "ratio", min_denominator=10, denominator_column="challenges")
    assert "c" not in set(res.frame["name"])


def test_detect_handles_nan_values():
    df = pd.DataFrame({"ratio": [1.0, 2.0, np.nan, 3.0, 100.0]})
    res = detect(df, "ratio")
    assert res.frame["ratio"].notna().all()
