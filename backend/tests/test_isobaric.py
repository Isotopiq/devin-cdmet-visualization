import pandas as pd
import pytest

from app.services.isobaric import (
    DEFAULT_ISOBARIC_RULE,
    apply_isobaric_substitution,
    find_isobaric_substitution_matches,
    parse_lipid_name,
)


def test_parse_lipid_name_handles_common_forms():
    assert parse_lipid_name("DG O-36:6") == {
        "class": "DG", "prefix": "O-", "carbon": 36, "db": 6,
    }
    assert parse_lipid_name("PE(O-18:1)") == {
        "class": "PE", "prefix": "O-", "carbon": 18, "db": 1,
    }
    assert parse_lipid_name("PC P-34:1") == {
        "class": "PC", "prefix": "P-", "carbon": 34, "db": 1,
    }
    assert parse_lipid_name("PC 34:2") == {
        "class": "PC", "prefix": None, "carbon": 34, "db": 2,
    }
    assert parse_lipid_name("PC 16:0/18:1") == {
        "class": "PC", "prefix": None, "carbon": 34, "db": 1,
    }
    assert parse_lipid_name("") is None


def test_default_op_rule_matches_multiple_classes():
    rules = [DEFAULT_ISOBARIC_RULE]

    assert find_isobaric_substitution_matches("DG O-36:6", "DG P-36:5", rules)
    assert find_isobaric_substitution_matches("PE O-18:1", "PE P-18:0", rules)
    assert find_isobaric_substitution_matches("PC O-34:2", "PC P-34:1", rules)
    # Also works reversed
    assert find_isobaric_substitution_matches("PC P-34:1", "PC O-34:2", rules)


def test_default_op_rule_rejects_non_matches():
    rules = [DEFAULT_ISOBARIC_RULE]

    # Different carbon count
    assert find_isobaric_substitution_matches("DG O-36:6", "DG P-34:5", rules) is None
    # Wrong DB offset
    assert find_isobaric_substitution_matches("DG O-36:6", "DG P-36:4", rules) is None
    # Class not in applicable_classes
    assert find_isobaric_substitution_matches("SM O-36:6", "SM P-36:5", rules) is None
    # No prefix
    assert find_isobaric_substitution_matches("PC 34:2", "PC 34:1", rules) is None


def test_custom_rule_is_class_agnostic():
    rules = [
        {
            "name": "custom hydroxy/epoxy",
            "applicable_classes": ["FA"],
            "prefix_pair": ["OH-", "Ep-"],
            "db_offset": 0,
            "carbon_count_match": True,
        }
    ]
    assert find_isobaric_substitution_matches("FA OH-18:1", "FA Ep-18:1", rules)
    # Same rule should not apply to PC
    assert find_isobaric_substitution_matches("PC OH-34:2", "PC Ep-34:2", rules) is None


def _make_lipid_df():
    samples = ["S1", "S2"]
    df = pd.DataFrame({
        "S1": [10.0, 20.0, 30.0, 40.0],
        "S2": [11.0, 21.0, 31.0, 41.0],
    })
    meta = [
        {"feature_id": "DG O-36:6", "mz": 600.123, "rt": 5.0, "class": "DG"},
        {"feature_id": "DG P-36:5", "mz": 600.123, "rt": 5.0, "class": "DG"},
        {"feature_id": "PE 18:0", "mz": 700.0, "rt": 6.0, "class": "PE"},
        {"feature_id": "PC O-34:2", "mz": 800.0, "rt": 7.0, "class": "PC"},
    ]
    return df, meta


def test_apply_flag_ambiguous():
    df, meta = _make_lipid_df()
    config = {
        "enable_isobaric_substitution_check": True,
        "feature_type": "lipid",
        "isobaric_substitution_mode": "flag_ambiguous",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
        "isobaric_clustering_enabled": True,
        "isobaric_mz_tolerance": 0.005,
        "isobaric_rt_tolerance": 0.2,
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    assert summary["enabled"]
    assert summary["groups_found"] == 1
    assert summary["rows_flagged"] == 2
    assert len(new_df) == 4
    assert new_meta[0]["isobaric_substitution_flag"] is True
    assert new_meta[0]["isobaric_substitution_group_id"].startswith("ISB_")
    assert new_meta[0]["isobaric_substitution_rule"] == DEFAULT_ISOBARIC_RULE["name"]
    assert new_meta[2]["isobaric_substitution_flag"] is None or new_meta[2].get("isobaric_substitution_flag") is False


def test_apply_report_combined():
    df, meta = _make_lipid_df()
    config = {
        "enable_isobaric_substitution_check": True,
        "feature_type": "lipid",
        "isobaric_substitution_mode": "report_combined",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
        "isobaric_clustering_enabled": True,
        "isobaric_mz_tolerance": 0.005,
        "isobaric_rt_tolerance": 0.2,
        "duplicate_handling": "mean",
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    assert summary["groups_found"] == 1
    assert summary["rows_combined"] == 2
    assert len(new_df) == 3
    combined = [m for m in new_meta if m.get("isobaric_substitution_resolution") == "report_combined"][0]
    assert "O-/P-" in combined["feature_id"]
    assert combined["isobaric_substitution_component_count"] == 2
    assert list(new_df.iloc[-1]) == pytest.approx([15.0, 16.0])


def test_apply_keep_separate_with_flag():
    df, meta = _make_lipid_df()
    # Give the O- row a higher score so alphabetical vs score can be tested
    meta[0]["mscore"] = 50.0
    meta[1]["mscore"] = 100.0
    config = {
        "enable_isobaric_substitution_check": True,
        "feature_type": "lipid",
        "isobaric_substitution_mode": "keep_separate_with_flag",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
        "isobaric_clustering_enabled": True,
        "isobaric_mz_tolerance": 0.005,
        "isobaric_rt_tolerance": 0.2,
        "isobaric_rollup_preference": "alphabetical",
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    assert len(new_df) == 4
    reps = [m for m in new_meta if m.get("isobaric_substitution_rollup_representative")]
    excluded = [m for m in new_meta if m.get("isobaric_substitution_rollup_exclude")]
    assert len(reps) == 1
    assert len(excluded) == 1
    assert reps[0]["feature_id"] == "DG O-36:6"  # alphabetically first


def test_apply_keep_separate_prefers_highest_score():
    df, meta = _make_lipid_df()
    meta[0]["mscore"] = 50.0
    meta[1]["mscore"] = 100.0
    config = {
        "enable_isobaric_substitution_check": True,
        "feature_type": "lipid",
        "isobaric_substitution_mode": "keep_separate_with_flag",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
        "isobaric_clustering_enabled": True,
        "isobaric_mz_tolerance": 0.005,
        "isobaric_rt_tolerance": 0.2,
        "isobaric_rollup_preference": "highest_mscore",
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    rep = [m for m in new_meta if m.get("isobaric_substitution_rollup_representative")][0]
    assert rep["feature_id"] == "DG P-36:5"


def test_apply_disabled_for_non_lipid():
    df, meta = _make_lipid_df()
    config = {
        "enable_isobaric_substitution_check": True,
        "feature_type": "metabolite",
        "isobaric_substitution_mode": "flag_ambiguous",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    assert summary["enabled"] is False
    assert len(new_df) == 4
    assert new_meta[0] == meta[0]


def test_apply_disabled_by_toggle():
    df, meta = _make_lipid_df()
    config = {
        "enable_isobaric_substitution_check": False,
        "feature_type": "lipid",
        "isobaric_substitution_rules": [DEFAULT_ISOBARIC_RULE],
    }
    new_df, new_meta, summary = apply_isobaric_substitution(df, meta, config)
    assert summary["enabled"] is False
    assert len(new_df) == 4
