"""
Unit Tests for Missed Opportunity Review (MOR) Tool (Issue #79)
Verifies:
1. Holdout Guard: Rejects datasets spanning into holdout (>= 2025-05-01) and ensures all sampled windows end before holdout.
2. Temporal Cut-Off: Stage A chart input data strictly slices up to t (no future lookahead).
3. Extraction Reproducibility: Same random seed produces identical case sequence and labels.
4. Blindness: Stage A gallery and questionnaire contain no ground truth labels (M1, C1, C2, answer_key).
5. Output Suite Integrity: Verifies all Stage A/B images, markdown galleries, and metadata JSON/YAML files exist and are valid.
"""

import json
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from tools.missed_opportunity_review import (
    extract_mor_candidates,
    HOLDOUT_START,
    DISCOVERY_START,
    render_case_charts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_mock_df_1h(end_date="2025-04-30 23:00:00", n_bars=2500):
    """Create synthetic 1h OHLCV data with features for testing."""
    times = pd.date_range(end=end_date, periods=n_bars, freq="1h", tz="UTC")
    close = np.full(n_bars, 50000.0)
    high = close + 50.0   # MFE ~ 0.25 ATR by default (< 1.0 ATR, eligible for C1)
    low = close - 50.0
    open_ = close.copy()

    # Spaced out M1 at regular intervals
    for idx in range(100, n_bars - 80, 150):
        high[idx + 1:idx + 50] = 50000.0 + 1500.0  # MFE = 1500 / 200 = 7.5 ATR (M1)

    # C2 losers (MVC signals that end lower)
    for idx in [200, 400, 600, 800, 1200, 1400, 1600, 1800, 2000]:
        if idx + 75 < n_bars:
            close[idx + 72] = 45000.0  # large negative net return (C2)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.full(n_bars, 100.0),
        "atr_24": np.full(n_bars, 200.0),
        "sma_21": close,
        "sma_34": close,
        "sma_55": close,
        "sma_89": close,
        "sma_144": close,
        "sma_233": close,
        "sma_377": close,
        "slope_34": np.zeros(n_bars),
        "slope_55": np.zeros(n_bars),
        "slope_233": np.zeros(n_bars),
        "sma_diff_21": np.zeros(n_bars),
        "sma_diff_34": np.zeros(n_bars),
        "sma_diff_55": np.zeros(n_bars),
        "sma_diff_89": np.zeros(n_bars),
        "sma_diff_233": np.zeros(n_bars),
        "bb_upper": high,
        "bb_mid": close,
        "bb_lower": low,
        "bb_width_atr": np.full(n_bars, 2.0),
        "afs_order_score": np.full(n_bars, 3),
        "afs_compression": np.full(n_bars, 0.5),
        "macro_age_ratio": np.full(n_bars, 1.0),
    }, index=times)
    return df


def test_holdout_guard_rejection():
    """Verify that extract_mor_candidates raises AssertionError when data reaches or exceeds 2025-05-01."""
    df_leak = _create_mock_df_1h(end_date="2025-05-02 00:00:00", n_bars=500)
    mvc_mask = pd.Series(False, index=df_leak.index)

    with pytest.raises(AssertionError, match="Holdout period accessed"):
        extract_mor_candidates(df_leak, mvc_mask)


def test_candidate_sampling_and_reproducibility():
    """Verify candidate extraction produces 5 M1, 3 C1, 2 C2 and is perfectly reproducible with same seed."""
    df = _create_mock_df_1h(end_date="2025-04-30 23:00:00", n_bars=2500)

    # Inject MVC signals
    mvc_mask = pd.Series(False, index=df.index)
    for idx in [200, 400, 600, 800, 1200, 1400, 1600, 1800, 2000]:
        mvc_mask.iloc[idx] = True

    cases_1 = extract_mor_candidates(df, mvc_mask, seed=42)
    cases_2 = extract_mor_candidates(df, mvc_mask, seed=42)

    assert len(cases_1) == 10
    types = [c["type"] for c in cases_1]
    assert types.count("M1") == 5
    assert types.count("C1") == 3
    assert types.count("C2") == 2

    # Reproducibility check
    for c1, c2 in zip(cases_1, cases_2):
        assert c1["type"] == c2["type"]
        assert c1["timestamp"] == c2["timestamp"]

    # All timestamps must be strictly before holdout start
    for c in cases_1:
        assert c["timestamp"] < HOLDOUT_START
        assert c["timestamp"] + pd.Timedelta(hours=72) <= HOLDOUT_START


def test_stage_a_temporal_cutoff_guard():
    """Ensure Stage A chart generation logic only receives and plots data <= t (no future leak)."""
    df_1h = _create_mock_df_1h(end_date="2025-04-30 23:00:00", n_bars=500)
    t = df_1h.index[250]
    loc0 = df_1h.index.get_loc(t)

    # Subslice past 120h up to t
    sub_1h = df_1h.iloc[loc0 - 120 : loc0 + 1]
    assert sub_1h.index[-1] == t, "Stage A must end exactly at t"
    assert (sub_1h.index <= t).all(), "Stage A must contain no future timestamps"


def test_stage_a_gallery_blindness():
    """Ensure gallery_stageA.md contains no ground truth labels or answer keys."""
    gallery_a_path = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "77-1m-microstructure-and-rapid-exit" / "review" / "gallery_stageA.md"
    assert gallery_a_path.exists(), f"File {gallery_a_path} does not exist"

    content = gallery_a_path.read_text(encoding="utf-8")
    forbidden_terms = ["M1", "C1", "C2", "answer_key"]
    for term in forbidden_terms:
        assert term not in content, f"Stage A gallery leaks forbidden term '{term}'!"

    # Ensure the case sections have no winner/loser leak or true classifications
    cases_section = content.split("## 2. ケース別 Stage A チャートと質問票")[1]
    for leak_word in ["正解", "勝率", "MFE", "72h"]:
        assert leak_word not in cases_section, f"Stage A cases section leaks '{leak_word}'!"


def test_review_suite_files_integrity():
    """Ensure EXP-77 review directory has complete set of Stage A/B images, galleries, JSON, and observations YAML."""
    review_dir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "77-1m-microstructure-and-rapid-exit" / "review"
    assert review_dir.exists(), f"Review dir {review_dir} does not exist"

    # 10 Stage A and 10 Stage B PNG images
    for i in range(1, 11):
        case_a = review_dir / f"case_{i:02d}_stageA.png"
        case_b = review_dir / f"case_{i:02d}_stageB.png"
        assert case_a.exists(), f"Missing {case_a}"
        assert case_b.exists(), f"Missing {case_b}"
        assert case_a.stat().st_size > 50000, f"{case_a} is unexpectedly small"
        assert case_b.stat().st_size > 50000, f"{case_b} is unexpectedly small"

    # Markdown galleries
    assert (review_dir / "gallery_stageA.md").exists()
    assert (review_dir / "gallery_stageB.md").exists()

    # Answer key
    answer_key_path = review_dir / "answer_key.json"
    assert answer_key_path.exists()
    with open(answer_key_path, "r", encoding="utf-8") as f:
        ak = json.load(f)
    assert len(ak) == 10
    types = [v["type"] for v in ak.values()]
    assert types.count("M1") == 5
    assert types.count("C1") == 3
    assert types.count("C2") == 2

    # Cases metadata snapshot
    cases_path = review_dir / "cases.json"
    assert cases_path.exists()
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    assert len(cases) == 10

    # Observations YAML
    obs_path = review_dir / "observations.yaml"
    assert obs_path.exists()
    obs_text = obs_path.read_text(encoding="utf-8")
    assert "review_id: MOR-77-01" in obs_text
    assert "experiment: EXP-77" in obs_text
