"""Isobaric substitution rule engine for lipidomics.

Detects lipid pairs that are chemically distinct but share identical formula, m/z
and RT and therefore cannot be resolved by MS1 data alone (e.g. plasmanyl O-
vs plasmenyl P- ether lipids).  The engine is rule-driven and applies only to
lipid datasets.
"""

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


#: Built-in default rule: plasmanyl (O-) / plasmenyl (P-) ether/vinyl-ether lipids.
DEFAULT_ISOBARIC_RULE: Dict[str, Any] = {
    "name": "O-/P- ether/vinyl-ether",
    "applicable_classes": ["PC", "PE", "PI", "PS", "PA", "PG", "DG", "TG"],
    "prefix_pair": ["O-", "P-"],
    "db_offset": 1,
    "carbon_count_match": True,
}


_LIPID_CLASS_RE = re.compile(r"^(?P<class>[A-Za-z]+)")
_PREFIX_RE = re.compile(r"^(?P<prefix>[A-Za-z]+-)")
_CHAIN_RE = re.compile(r"(?P<carbon>\d+):(?P<db>\d+)")


def _strip_lyso_ether_prefix(cls: str) -> str:
    """Return a core class for names like LysoPE / EtherPC / PlasmPC."""
    return re.sub(r"^(lyso|ether|plasm)(enyl|anyl)?", "", cls, flags=re.IGNORECASE)


def parse_lipid_name(name: str) -> Optional[Dict[str, Any]]:
    """Parse a LIPID MAPS-style shorthand lipid name into class/prefix/C/DB.

    Supports forms such as:
        - "DG O-36:6"
        - "PE(O-18:1)"
        - "PC 16:0/18:1"
        - "PC P-34:1"
    For multi-chain names the carbon and DB values are summed.
    """
    if not name or not isinstance(name, str):
        return None

    name = name.strip()

    m = _LIPID_CLASS_RE.match(name)
    if not m:
        return None

    cls = m.group("class")
    rest = name[m.end():].strip()
    rest = re.sub(r"^[\s\(\[\{]+", "", rest)
    rest = re.sub(r"[\)\]\}]+$", "", rest)

    prefix = None
    pm = _PREFIX_RE.match(rest)
    if pm:
        prefix = pm.group("prefix")
        rest = rest[pm.end():].strip()

    chains = _CHAIN_RE.findall(rest)
    if not chains:
        # Some names put the prefix after the first slash, e.g. "PC 16:0/P-18:1"
        # Try to detect a prefix token anywhere in the remainder.
        pm2 = re.search(r"(?P<prefix>[A-Z]-)", rest)
        if pm2:
            prefix = pm2.group("prefix")
        chains = _CHAIN_RE.findall(rest)
        if not chains:
            return None

    carbon = sum(int(c) for c, _ in chains)
    db = sum(int(d) for _, d in chains)

    return {
        "class": cls,
        "prefix": prefix,
        "carbon": carbon,
        "db": db,
    }


def _class_matches(cls: str, applicable_classes: Optional[List[str]]) -> bool:
    if not applicable_classes:
        return True
    needles = {c.strip().lower() for c in applicable_classes if c}
    variants = {cls.lower(), _strip_lyso_ether_prefix(cls).lower()}
    return not needles.isdisjoint(variants)


def _score_for_representative(meta: Dict[str, Any]) -> float:
    """Return a numeric score for choosing a representative row."""
    for key in ("mscore", "id_score", "top_candidate_id_score", "peak_rating"):
        val = meta.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def find_isobaric_substitution_matches(
    name_a: str,
    name_b: str,
    rule_table: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Check whether two lipid names match any active isobaric substitution rule.

    Returns the matched rule (including a "matched_prefixes" key) or None.
    """
    parsed_a = parse_lipid_name(name_a)
    parsed_b = parse_lipid_name(name_b)
    if not parsed_a or not parsed_b:
        return None

    for rule in rule_table or [DEFAULT_ISOBARIC_RULE]:
        applicable = rule.get("applicable_classes") or []
        if not _class_matches(parsed_a["class"], applicable):
            continue
        if not _class_matches(parsed_b["class"], applicable):
            continue

        pair = [str(p).strip() for p in rule.get("prefix_pair", [])]
        if len(pair) != 2:
            continue

        prefix_a = parsed_a["prefix"]
        prefix_b = parsed_b["prefix"]
        if {prefix_a, prefix_b} != set(pair):
            continue

        if prefix_a == pair[0] and prefix_b == pair[1]:
            order = pair
        else:
            order = [pair[1], pair[0]]

        if rule.get("carbon_count_match", True):
            if parsed_a["carbon"] != parsed_b["carbon"]:
                continue

        db_offset_raw = rule.get("db_offset", 1)
        db_offset = int(db_offset_raw) if db_offset_raw is not None else 1
        if abs(parsed_a["db"] - parsed_b["db"]) != db_offset:
            continue

        matched = dict(rule)
        matched["matched_prefixes"] = order
        return matched

    return None


def _safe_float(value, default: float = 0.0) -> float:
    try:
        v = float(value)
        if pd.isna(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _union_find(n: int):
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    return find, union


def _cluster_indices(
    feature_metadata: List[Dict[str, Any]],
    mz_tolerance: float,
    rt_tolerance: float,
    use_rt: bool,
) -> List[List[int]]:
    """Group rows by m/z (+ optional RT) tolerance."""
    n = len(feature_metadata)
    if n == 0:
        return []

    def _mz(i: int) -> float:
        return _safe_float(feature_metadata[i].get("mz"), 0.0)

    order = sorted(range(n), key=_mz)
    find, union = _union_find(n)

    for idx, i in enumerate(order):
        mz_i = _mz(i)
        rt_i = _safe_float(feature_metadata[i].get("rt"), 0.0) if use_rt else None
        j = idx + 1
        while j < len(order):
            k = order[j]
            if abs(_mz(k) - mz_i) > mz_tolerance:
                break
            if use_rt:
                rt_k = _safe_float(feature_metadata[k].get("rt"), 0.0)
                if abs(rt_k - rt_i) <= rt_tolerance:
                    union(i, k)
            else:
                union(i, k)
            j += 1

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _candidate_name(meta: Dict[str, Any]) -> str:
    return str(
        meta.get("top_candidate_name")
        or meta.get("lipid_name")
        or meta.get("feature_id")
        or ""
    ).strip()


def _lipid_class_for_rule(meta: Dict[str, Any]) -> str:
    return (
        meta.get("top_candidate_class")
        or meta.get("class")
        or meta.get("lipid_class")
        or ""
    ).strip()


def _combine_feature_id(component_metas: List[Dict[str, Any]], rule: Dict[str, Any]) -> str:
    """Generate an ambiguous composition ID for report_combined mode."""
    cls = _lipid_class_for_rule(component_metas[0]) or parse_lipid_name(_candidate_name(component_metas[0]))["class"] or "Lipid"
    prefixes = rule.get("matched_prefixes") or rule.get("prefix_pair", [])
    parsed = []
    for meta in component_metas:
        name = _candidate_name(meta)
        p = parse_lipid_name(name)
        if p and p["prefix"]:
            parsed.append(p)

    # Sort parsed entries by prefix order from the rule so the notation is stable.
    def prefix_index(p):
        try:
            return prefixes.index(p["prefix"])
        except ValueError:
            return 99

    parsed.sort(key=prefix_index)

    if not parsed:
        return f"{cls}({rule.get('name', 'isobaric')})"

    carbons = {p["carbon"] for p in parsed}
    if len(carbons) == 1:
        carbon = list(carbons)[0]
        dbs = "/".join(str(p["db"]) for p in parsed)
        prefix_tokens = "/".join(str(p["prefix"]) for p in parsed)
        return f"{cls}({prefix_tokens}{carbon}:{dbs})"
    else:
        parts = "/".join(f"{p['prefix']}{p['carbon']}:{p['db']}" for p in parsed)
        return f"{cls}({parts})"


def apply_isobaric_substitution(
    df: pd.DataFrame,
    feature_metadata: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any]]:
    """Apply the isobaric substitution rule engine to a lipid DataFrame.

    Returns the updated DataFrame, updated feature_metadata, and a summary dict.
    """
    summary = {
        "enabled": False,
        "mode": "none",
        "rule_count": 0,
        "groups_found": 0,
        "rows_flagged": 0,
        "rows_combined": 0,
    }

    if not config.get("enable_isobaric_substitution_check"):
        return df, feature_metadata, summary

    feature_type = config.get("feature_type", "")
    if feature_type != "lipid":
        return df, feature_metadata, summary

    rules = config.get("isobaric_substitution_rules") or [DEFAULT_ISOBARIC_RULE]
    mode = config.get("isobaric_substitution_mode", "flag_ambiguous")
    merge_method = config.get("duplicate_handling", "mean")
    if merge_method not in ("mean", "sum"):
        merge_method = "mean"
    rollup_preference = config.get("isobaric_rollup_preference", "alphabetical")
    mz_tol = float(config.get("isobaric_mz_tolerance", 0.005))
    rt_tol = float(config.get("isobaric_rt_tolerance", 0.2))
    cluster_enabled = bool(config.get("isobaric_clustering_enabled", True))

    summary["enabled"] = True
    summary["mode"] = mode
    summary["rule_count"] = len(rules)

    n = len(feature_metadata)
    if n == 0 or df.empty:
        return df, feature_metadata, summary

    # Ensure metadata is mutable copies.
    meta = [dict(m) for m in feature_metadata]

    for m in meta:
        m.setdefault("isobaric_substitution_flag", False)
        m.setdefault("isobaric_substitution_rule", None)
        m.setdefault("isobaric_substitution_group_id", None)
        m.setdefault("isobaric_substitution_resolution", None)
        m.setdefault("isobaric_substitution_rollup_representative", False)
        m.setdefault("isobaric_substitution_rollup_exclude", False)

    clusters = _cluster_indices(meta, mz_tol, rt_tol, cluster_enabled)

    find, union = _union_find(n)

    for cluster in clusters:
        if len(cluster) < 2:
            continue
        for i_idx in range(len(cluster)):
            for j_idx in range(i_idx + 1, len(cluster)):
                i, j = cluster[i_idx], cluster[j_idx]
                name_i = _candidate_name(meta[i])
                name_j = _candidate_name(meta[j])
                if not name_i or not name_j:
                    continue
                match = find_isobaric_substitution_matches(name_i, name_j, rules)
                if match:
                    union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    isobaric_groups = {
        root: idxs for root, idxs in groups.items() if len(idxs) >= 2
    }

    if not isobaric_groups:
        return df, feature_metadata, summary

    summary["groups_found"] = len(isobaric_groups)

    flagged_indices: set = set()
    group_counter = 0

    if mode == "flag_ambiguous":
        for root, idxs in isobaric_groups.items():
            group_counter += 1
            # Determine the matching rule from the first pair.
            match = find_isobaric_substitution_matches(_candidate_name(meta[idxs[0]]), _candidate_name(meta[idxs[1]]), rules)
            rule_name = match.get("name", "isobaric") if match else "isobaric"
            for i in idxs:
                flagged_indices.add(i)
                meta[i]["isobaric_substitution_flag"] = True
                meta[i]["isobaric_substitution_rule"] = rule_name
                meta[i]["isobaric_substitution_group_id"] = f"ISB_{group_counter}"
                meta[i]["isobaric_substitution_resolution"] = "flag_ambiguous"
                meta[i]["isobaric_substitution_rollup_representative"] = False
                meta[i]["isobaric_substitution_rollup_exclude"] = False

        summary["rows_flagged"] = len(flagged_indices)
        return df.reset_index(drop=True), meta, summary

    if mode == "report_combined":
        keep_rows: List[int] = []
        combined_dfs: List[pd.DataFrame] = []
        combined_meta: List[Dict[str, Any]] = []

        for i in range(n):
            root = find(i)
            if root not in isobaric_groups or i != min(isobaric_groups[root]):
                if root not in isobaric_groups:
                    keep_rows.append(i)
                continue

            if i == min(isobaric_groups[root]):
                group_counter += 1
                idxs = isobaric_groups[root]
                match = find_isobaric_substitution_matches(_candidate_name(meta[idxs[0]]), _candidate_name(meta[idxs[1]]), rules)
                rule_name = match.get("name", "isobaric") if match else "isobaric"

                comp_metas = [meta[k] for k in idxs]
                component_names = [_candidate_name(m) for m in comp_metas]
                new_meta = deepcopy(comp_metas[0])
                new_meta["feature_id"] = _combine_feature_id(comp_metas, match or rules[0])
                new_meta["isobaric_substitution_flag"] = True
                new_meta["isobaric_substitution_rule"] = rule_name
                new_meta["isobaric_substitution_group_id"] = f"ISB_{group_counter}"
                new_meta["isobaric_substitution_resolution"] = "report_combined"
                new_meta["isobaric_substitution_rollup_representative"] = True
                new_meta["isobaric_substitution_rollup_exclude"] = False
                new_meta["isobaric_substitution_component_names"] = component_names
                new_meta["isobaric_substitution_component_count"] = len(comp_metas)

                sub_df = df.iloc[idxs]
                if merge_method == "sum":
                    merged = sub_df.sum(numeric_only=True)
                else:
                    merged = sub_df.mean(numeric_only=True)
                merged_df = pd.DataFrame([merged], columns=df.columns)

                combined_dfs.append(merged_df)
                combined_meta.append(new_meta)
                summary["rows_combined"] += len(idxs)
                flagged_indices.update(idxs)

        new_df = pd.concat([df.iloc[keep_rows]] + combined_dfs, ignore_index=True)
        new_meta = [meta[i] for i in keep_rows] + combined_meta

        summary["rows_flagged"] = len(flagged_indices)
        return new_df.reset_index(drop=True), new_meta, summary

    if mode == "keep_separate_with_flag":
        for root, idxs in isobaric_groups.items():
            group_counter += 1
            match = find_isobaric_substitution_matches(_candidate_name(meta[idxs[0]]), _candidate_name(meta[idxs[1]]), rules)
            rule_name = match.get("name", "isobaric") if match else "isobaric"

            if rollup_preference == "highest_mscore":
                chosen = max(idxs, key=lambda k: _score_for_representative(meta[k]))
            else:  # alphabetical by candidate name
                chosen = min(idxs, key=lambda k: _candidate_name(meta[k]))

            for i in idxs:
                flagged_indices.add(i)
                meta[i]["isobaric_substitution_flag"] = True
                meta[i]["isobaric_substitution_rule"] = rule_name
                meta[i]["isobaric_substitution_group_id"] = f"ISB_{group_counter}"
                meta[i]["isobaric_substitution_resolution"] = "keep_separate_with_flag"
                if i == chosen:
                    meta[i]["isobaric_substitution_rollup_representative"] = True
                    meta[i]["isobaric_substitution_rollup_exclude"] = False
                else:
                    meta[i]["isobaric_substitution_rollup_representative"] = False
                    meta[i]["isobaric_substitution_rollup_exclude"] = True

        summary["rows_flagged"] = len(flagged_indices)
        return df.reset_index(drop=True), meta, summary

    # Unknown mode: fall through to flag_ambiguous behavior (safest).
    return df.reset_index(drop=True), meta, summary
