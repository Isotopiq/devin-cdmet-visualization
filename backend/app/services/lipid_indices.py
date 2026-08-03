import re
import numpy as np
from scipy import stats as scipy_stats
from statsmodels.stats.multitest import multipletests


_CHAIN_RE = re.compile(r"([A-Za-z]?)-?(\d+):(\d+)")


def _safe_div(num: np.ndarray, den: np.ndarray, fill: float = 0.0) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den, fill)


def _ttest(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a)[np.isfinite(a)]
    b = np.asarray(b)[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return 1.0
    try:
        _, p = scipy_stats.ttest_ind(a, b, equal_var=False, nan_policy="omit")
    except Exception:
        return 1.0
    if not np.isfinite(p):
        return 1.0
    return float(p)


def _bh(pvals: list) -> list:
    if not pvals:
        return []
    clean = [float(p) if np.isfinite(p) and p > 0 else 1.0 for p in pvals]
    _, padj, _, _ = multipletests(clean, method="fdr_bh")
    return padj.tolist()


def _normalize_class(cls: str) -> str:
    c = cls.upper().replace("-", "")
    mapping = {
        "PCCER": "PC-Cer",
        "PECER": "PE-Cer",
        "HEXCER": "HexCer",
        "HEX2CER": "Hex2Cer",
        "SHEXCER": "SHexCer",
        "CERP": "CerP",
        "CHO": "Chol",
        "COH": "Chol",
        "CHOL": "Chol",
        "CAR": "CAR",
        "CARNITINE": "CAR",
        "FA": "FA",
        "FAA": "FA",
        "CL": "CL",
    }
    return mapping.get(c, c)


def _parse_chains(name: str):
    paren = re.search(r"\(([^)]+)\)", name)
    if not paren:
        return []
    chain_str = paren.group(1)
    out = []
    for token in re.split(r"[_/]+", chain_str):
        token = re.sub(r"\(.*?\)", "", token).strip()
        m = _CHAIN_RE.match(token)
        if not m:
            continue
        prefix = m.group(1).upper()
        carbon = int(m.group(2))
        db = int(m.group(3))
        out.append({
            "carbon": carbon,
            "db": db,
            "ether": prefix in ("O", "P"),
            "plasmalogen": prefix == "P",
        })
    return out


def _parse_feature(name: str):
    m = re.match(r"^([A-Za-z0-9\-]+?)(?:\(|:|\s|$)", name)
    cls = m.group(1) if m else "Unknown"
    return _normalize_class(cls), _parse_chains(name)


def _build_class_index(major: str, lysos: tuple):
    def getter(class_sums):
        total = np.zeros(next(iter(class_sums.values())).shape)
        for c in [major] + list(lysos):
            total = total + class_sums.get(c, np.zeros_like(total))
        return total
    return getter


def _collect_sums(df, feature_metadata, samples):
    n = len(samples)
    class_sums = {}
    # extended chain/property buckets
    prop_keys = [
        "saturated", "monounsat", "polyunsat",
        "n3", "n6",
        "c12", "c14", "c16", "c18", "c20", "c22", "c24",
        "c12_0", "c14_0", "c16_0", "c18_0",
        "c16_1", "c18_1", "c18_2", "c18_3",
        "c20_4", "c20_5", "c22_6",
        "ether", "plasmalogen",
        "c18_unsat", "c18_sat",
        "epa", "ara", "dha",
        "peroxidation_index_num", "chain_length_num",
    ]
    prop = {k: np.zeros(n) for k in prop_keys}
    # class-specific unsat/sat flags
    cls_unsat = {}
    cls_sat = {}
    for c in ["PC", "PE", "PI", "PS", "PG", "PA"]:
        cls_unsat[c] = np.zeros(n)
        cls_sat[c] = np.zeros(n)

    for i, row_meta in enumerate(feature_metadata):
        if i >= len(df):
            continue
        name = row_meta.get("feature_id", "") or row_meta.get("name", "")
        cls, chains = _parse_feature(name)
        vals = df.iloc[i].values.astype(float).copy()
        class_sums[cls] = class_sums.get(cls, np.zeros(n)) + vals

        if not chains:
            continue

        dbs = [ch["db"] for ch in chains]
        carbons = [ch["carbon"] for ch in chains]
        avg_db = float(np.mean(dbs))
        avg_c = float(np.mean(carbons))
        max_db = max(dbs)
        any_sat = all(d == 0 for d in dbs)
        any_unsat = any(d >= 1 for d in dbs)
        any_poly = any(d >= 2 for d in dbs)
        any_mono = any_unsat and max_db == 1
        if any_sat:
            prop["saturated"] += vals
        if any_mono:
            prop["monounsat"] += vals
        if any_poly:
            prop["polyunsat"] += vals

        prop["peroxidation_index_num"] += vals * avg_db
        prop["chain_length_num"] += vals * avg_c

        any_ether = any(ch["ether"] for ch in chains)
        any_plas = any(ch["plasmalogen"] for ch in chains)
        if any_ether:
            prop["ether"] += vals
        if any_plas:
            prop["plasmalogen"] += vals

        if any((ch["carbon"] == 18 and ch["db"] >= 1) for ch in chains):
            prop["c18_unsat"] += vals
        if any((ch["carbon"] == 18 and ch["db"] == 0) for ch in chains):
            prop["c18_sat"] += vals

        for ch in chains:
            c, db = ch["carbon"], ch["db"]
            if c == 12:
                prop["c12"] += vals
            elif c == 14:
                prop["c14"] += vals
            elif c == 16:
                prop["c16"] += vals
            elif c == 18:
                prop["c18"] += vals
            elif c == 20:
                prop["c20"] += vals
            elif c == 22:
                prop["c22"] += vals
            elif c == 24:
                prop["c24"] += vals

            if c == 12 and db == 0:
                prop["c12_0"] += vals
            if c == 14 and db == 0:
                prop["c14_0"] += vals
            if c == 16 and db == 0:
                prop["c16_0"] += vals
            if c == 18 and db == 0:
                prop["c18_0"] += vals
            if c == 16 and db == 1:
                prop["c16_1"] += vals
            if c == 18 and db == 1:
                prop["c18_1"] += vals
            if c == 18 and db == 2:
                prop["c18_2"] += vals
            if c == 18 and db == 3:
                prop["c18_3"] += vals
            if c == 20 and db == 4:
                prop["c20_4"] += vals
            if c == 20 and db == 5:
                prop["epa"] += vals
                prop["c20_5"] += vals
            if c == 22 and db == 6:
                prop["dha"] += vals
                prop["c22_6"] += vals

        # rough omega classification based on common lipid names
        n3 = any((ch["carbon"], ch["db"]) in [(18, 3), (18, 4), (20, 5), (22, 5), (22, 6)] for ch in chains)
        n6 = any((ch["carbon"], ch["db"]) in [(18, 2), (20, 3), (20, 4), (22, 4)] for ch in chains)
        if n3:
            prop["n3"] += vals
        if n6:
            prop["n6"] += vals

        if cls in cls_unsat:
            if any_unsat:
                cls_unsat[cls] += vals
            if any_sat:
                cls_sat[cls] += vals

    return class_sums, prop, cls_unsat, cls_sat


def _ratio_index(name, cat, num_samples, den_samples, a_idx, b_idx, desc, interp_high, interp_low):
    n = len(num_samples)
    ratio = _safe_div(num_samples, np.where(den_samples > 0, den_samples, 0), fill=np.nan)
    a_vals = ratio[a_idx]
    b_vals = ratio[b_idx]
    a_vals = a_vals[np.isfinite(a_vals)]
    b_vals = b_vals[np.isfinite(b_vals)]
    p = _ttest(a_vals, b_vals)
    mean_a = float(np.nanmean(a_vals)) if len(a_vals) else 0.0
    mean_b = float(np.nanmean(b_vals)) if len(b_vals) else 0.0
    if mean_a > 0 and mean_b > 0:
        log2fc = float(np.log2(mean_b / mean_a))
    else:
        log2fc = 0.0
    interp = interp_high if log2fc > 0 else (interp_low if log2fc < 0 else "No directional change")
    return {
        "name": name,
        "category": cat,
        "description": desc,
        "log2fc": log2fc,
        "pvalue": p,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "interpretation": interp,
    }


def _label_interpretations(raw, group_a, group_b):
    """Replace A/B placeholders in interpretation strings with actual group names."""
    for r in raw:
        interp = r["interpretation"].replace(" in B", f" in {group_b}")
        # For negative log2fc, "Lower X in B" is equivalent to "Higher X in A"
        if r["log2fc"] < 0 and interp.startswith("Lower"):
            interp = ("Higher " + interp[6:]).replace(f" in {group_b}", f" in {group_a}", 1)
        r["interpretation"] = interp
    return raw


def compute_functional_indices(df, feature_metadata, sample_meta, group_a, group_b):
    samples = df.columns.tolist()
    n = len(samples)
    a_idx = [i for i, c in enumerate(samples) if sample_meta.get(c) == group_a]
    b_idx = [i for i, c in enumerate(samples) if sample_meta.get(c) == group_b]
    if not a_idx or not b_idx:
        return []

    class_sums, prop, cls_unsat, cls_sat = _collect_sums(df, feature_metadata, samples)
    if not class_sums:
        return []

    total = np.zeros(n)
    for v in class_sums.values():
        total += v

    def get(cl):
        return class_sums.get(cl, np.zeros(n))

    def csum(classes):
        return sum((class_sums.get(c, np.zeros(n)) for c in classes), np.zeros(n))

    pl = csum(["PC", "PE", "PI", "PS", "PG", "PA", "LPC", "LPE", "LPI", "LPS", "LPG", "LPA", "CL"])
    lysos = csum(["LPC", "LPE", "LPI", "LPS", "LPG", "LPA"])
    neutral = csum(["TG", "DG", "CE", "Chol"])
    polar = pl + csum(["SM", "Cer", "HexCer", "Hex2Cer", "SHexCer", "CerP"])
    membrane_unsat = sum((cls_unsat[c] for c in ["PC", "PE", "PI", "PS", "PG", "PA"]), np.zeros(n))
    membrane_sat = sum((cls_sat[c] for c in ["PC", "PE", "PI", "PS", "PG", "PA"]), np.zeros(n))

    raw = []
    # Structural/compositional
    raw.append(_ratio_index("PC unsat/sat", "Structural", membrane_unsat, membrane_sat, a_idx, b_idx,
                            "Unsaturated / saturated phospholipid species",
                            "Higher membrane fluidity in B", "Lower membrane fluidity in B"))
    raw.append(_ratio_index("PE/PC", "Structural", get("PE"), get("PC"), a_idx, b_idx,
                            "Phosphatidylethanolamine / phosphatidylcholine ratio",
                            "Higher PE relative to PC in B", "Lower PE relative to PC in B"))
    raw.append(_ratio_index("PI/PL", "Structural", get("PI"), pl, a_idx, b_idx,
                            "Phosphatidylinositol fraction of phospholipids",
                            "Higher PI content in B", "Lower PI content in B"))
    raw.append(_ratio_index("PS/PL", "Structural", get("PS"), pl, a_idx, b_idx,
                            "Phosphatidylserine fraction of phospholipids",
                            "Higher PS content in B", "Lower PS content in B"))
    raw.append(_ratio_index("PG/PL", "Structural", get("PG"), pl, a_idx, b_idx,
                            "Phosphatidylglycerol fraction of phospholipids",
                            "Higher PG content in B", "Lower PG content in B"))
    raw.append(_ratio_index("PA/PL", "Structural", get("PA"), pl, a_idx, b_idx,
                            "Phosphatidic acid fraction of phospholipids",
                            "Higher PA content in B", "Lower PA content in B"))
    raw.append(_ratio_index("SM/PL", "Structural", get("SM"), pl, a_idx, b_idx,
                            "Sphingomyelin fraction of phospholipids",
                            "Higher SM content in B", "Lower SM content in B"))
    raw.append(_ratio_index("Cer/PL", "Structural", get("Cer") + get("HexCer"), pl, a_idx, b_idx,
                            "Ceramide + hexosylceramide fraction of phospholipids",
                            "Higher ceramide content in B", "Lower ceramide content in B"))
    raw.append(_ratio_index("CE/PL", "Structural", get("CE"), pl, a_idx, b_idx,
                            "Cholesterol ester / phospholipid ratio",
                            "Higher CE relative to PL in B", "Lower CE relative to PL in B"))
    raw.append(_ratio_index("Cer/SM", "Structural", get("Cer") + get("HexCer"), get("SM"), a_idx, b_idx,
                            "Ceramide / sphingomyelin ratio",
                            "Higher ceramide-to-SM in B (sphingolipid turnover)", "Lower ceramide-to-SM in B"))
    raw.append(_ratio_index("Neutral/Polar", "Structural", neutral, polar, a_idx, b_idx,
                            "Neutral (TG/DG/CE/Chol) / polar (PL/SM/Cer) lipids",
                            "Shift toward neutral/storage lipids in B", "Shift toward polar/membrane lipids in B"))

    # Signaling/remodeling
    raw.append(_ratio_index("LPC/PC", "Signaling", get("LPC"), get("PC"), a_idx, b_idx,
                            "Lysophosphatidylcholine / phosphatidylcholine ratio",
                            "Higher LPC hydrolysis/signaling in B", "Lower LPC in B"))
    raw.append(_ratio_index("LPE/PE", "Signaling", get("LPE"), get("PE"), a_idx, b_idx,
                            "Lysophosphatidylethanolamine / PE ratio",
                            "Higher LPE signaling in B", "Lower LPE in B"))
    raw.append(_ratio_index("LPA/PA", "Signaling", get("LPA"), get("PA"), a_idx, b_idx,
                            "Lysophosphatidic acid / PA ratio",
                            "Higher LPA signaling in B", "Lower LPA in B"))
    raw.append(_ratio_index("Lyso/PL", "Signaling", lysos, pl, a_idx, b_idx,
                            "Total lysophospholipids / phospholipids",
                            "Higher lysophospholipid signaling in B", "Lower lysophospholipids in B"))
    raw.append(_ratio_index("DG/PL", "Signaling", get("DG"), pl, a_idx, b_idx,
                            "Diacylglycerol / phospholipid ratio",
                            "Higher DAG signaling in B", "Lower DAG in B"))

    # Energy/storage
    raw.append(_ratio_index("DG/TG", "Energy", get("DG"), get("TG"), a_idx, b_idx,
                            "Diacylglycerol / triacylglycerol ratio",
                            "Higher DG relative to stored TG in B", "Lower DG/TG in B"))
    raw.append(_ratio_index("TG/PL", "Energy", get("TG"), pl, a_idx, b_idx,
                            "Triacylglycerol / phospholipid ratio",
                            "Higher storage TG in B", "Lower storage TG in B"))
    raw.append(_ratio_index("Storage index", "Energy", get("TG") + get("DG"), total, a_idx, b_idx,
                            "(TG + DG) / total lipids",
                            "Higher storage lipid pool in B", "Lower storage lipids in B"))
    raw.append(_ratio_index("Energy load", "Energy", get("TG") + get("DG") + get("CE"), total, a_idx, b_idx,
                            "(TG + DG + CE) / total lipids",
                            "Higher energy storage load in B", "Lower energy storage load in B"))
    raw.append(_ratio_index("Acylcarnitine fraction", "Energy", get("CAR"), total, a_idx, b_idx,
                            "Acylcarnitines / total lipids",
                            "Higher fatty acid oxidation substrate in B", "Lower acylcarnitines in B"))

    # Chain-remodeling / enzyme proxies
    raw.append(_ratio_index("SCD16 index", "Chain remodeling", prop["c16_1"], prop["c16_0"], a_idx, b_idx,
                            "Stearoyl-CoA desaturase-1 proxy: C16:1/C16:0",
                            "Higher SCD1 activity in B", "Lower SCD16 index in B"))
    raw.append(_ratio_index("SCD18 index", "Chain remodeling", prop["c18_1"], prop["c18_0"], a_idx, b_idx,
                            "Stearoyl-CoA desaturase proxy: C18:1/C18:0",
                            "Higher SCD activity in B", "Lower SCD18 index in B"))
    raw.append(_ratio_index("Elovl6 index", "Chain remodeling", prop["c18_0"], prop["c16_0"], a_idx, b_idx,
                            "Elongase-6 proxy: C18:0/C16:0",
                            "Higher elongation in B", "Lower elongation in B"))
    raw.append(_ratio_index("Delta-5 desaturase index", "Chain remodeling", prop["c20_4"], prop["c18_2"], a_idx, b_idx,
                            "ARA/LA proxy of delta-5 desaturation/elongation",
                            "Higher ARA production in B", "Lower ARA production in B"))
    raw.append(_ratio_index("Delta-6 desaturase index", "Chain remodeling", prop["c18_3"], prop["c18_2"], a_idx, b_idx,
                            "ALA/LA proxy of delta-6 desaturation",
                            "Higher ALA conversion in B", "Lower delta-6 index in B"))
    raw.append(_ratio_index("Elovl2/5 index", "Chain remodeling", prop["c22_6"], prop["c20_5"], a_idx, b_idx,
                            "DHA/EPA proxy of very-long-chain elongation",
                            "Higher DHA synthesis in B", "Lower DHA synthesis in B"))
    # Structural/oxidative
    raw.append(_ratio_index("Peroxidation index", "Oxidative stress", prop["peroxidation_index_num"], total, a_idx, b_idx,
                            "Average double-bond content (intensity-weighted)",
                            "Higher peroxidation susceptibility in B", "Lower peroxidation index in B"))
    raw.append(_ratio_index("Average chain length", "Structural", prop["chain_length_num"], total, a_idx, b_idx,
                            "Intensity-weighted average acyl carbon chain length",
                            "Longer average chains in B", "Shorter average chains in B"))
    raw.append(_ratio_index("CL/PL", "Mitochondrial", get("CL"), pl, a_idx, b_idx,
                            "Cardiolipin / phospholipid ratio",
                            "Higher mitochondrial CL in B", "Lower CL/PL in B"))
    raw.append(_ratio_index("CL fraction", "Mitochondrial", get("CL"), total, a_idx, b_idx,
                            "Cardiolipin fraction of total lipids",
                            "Higher CL in B", "Lower CL fraction in B"))
    raw.append(_ratio_index("Free cholesterol/PL", "Structural", get("Chol"), pl, a_idx, b_idx,
                            "Free cholesterol / phospholipid ratio (membrane packing)",
                            "Higher membrane packing/raft signal in B", "Lower FC/PL in B"))
    raw.append(_ratio_index("n6/n3 ratio", "Inflammation", prop["n6"], prop["n3"], a_idx, b_idx,
                            "Omega-6 / omega-3 balance",
                            "Higher pro-inflammatory n6 relative to n3 in B", "Lower n6/n3 in B"))
    raw.append(_ratio_index("ARA fraction", "Inflammation", prop["c20_4"], total, a_idx, b_idx,
                            "Arachidonic acid (20:4n6) feature intensity / total",
                            "Higher ARA precursor pool in B", "Lower ARA fraction in B"))

    pvals = [r["pvalue"] for r in raw]
    padjs = _bh(pvals)
    for r, p in zip(raw, padjs):
        r["padj"] = p
    _label_interpretations(raw, group_a, group_b)
    return raw


def compute_food_profile_indices(df, feature_metadata, sample_meta, group_a, group_b):
    samples = df.columns.tolist()
    n = len(samples)
    a_idx = [i for i, c in enumerate(samples) if sample_meta.get(c) == group_a]
    b_idx = [i for i, c in enumerate(samples) if sample_meta.get(c) == group_b]
    if not a_idx or not b_idx:
        return []

    class_sums, prop, _, _ = _collect_sums(df, feature_metadata, samples)
    if not class_sums:
        return []

    total = np.zeros(n)
    for v in class_sums.values():
        total += v

    raw = []
    raw.append(_ratio_index("SFA fraction", "Compositional balance", prop["saturated"], total, a_idx, b_idx,
                            "Saturated-feature intensity / total",
                            "Higher saturated lipid content in B", "Lower saturated lipids in B"))
    raw.append(_ratio_index("MUFA fraction", "Compositional balance", prop["monounsat"], total, a_idx, b_idx,
                            "Monounsaturated-feature intensity / total",
                            "Higher MUFA content in B", "Lower MUFA content in B"))
    raw.append(_ratio_index("PUFA fraction", "Compositional balance", prop["polyunsat"], total, a_idx, b_idx,
                            "Polyunsaturated-feature intensity / total",
                            "Higher PUFA content in B", "Lower PUFA content in B"))
    raw.append(_ratio_index("MUFA/SFA", "Compositional balance", prop["monounsat"], prop["saturated"], a_idx, b_idx,
                            "Monounsaturated / saturated feature ratio",
                            "Higher relative MUFA in B", "Lower relative MUFA in B"))
    raw.append(_ratio_index("PUFA/SFA", "Oxidative stability", prop["polyunsat"], prop["saturated"], a_idx, b_idx,
                            "Polyunsaturated / saturated feature ratio",
                            "Higher PUFA/SFA in B (more oxidizable)", "Lower PUFA/SFA in B"))
    raw.append(_ratio_index("C18 desaturation index", "Chain remodeling", prop["c18_unsat"], prop["c18_sat"], a_idx, b_idx,
                            "(C18:1+18:2+18:3) / C18:0",
                            "Higher C18 desaturation in B", "Lower C18 desaturation in B"))
    raw.append(_ratio_index("EPA/ARA", "Omega balance", prop["epa"], prop["ara"], a_idx, b_idx,
                            "Eicosapentaenoic (20:5) / arachidonic (20:4) feature ratio",
                            "Higher anti-inflammatory n3 precursor in B", "Lower EPA/ARA in B"))
    raw.append(_ratio_index("DHA/EPA", "Omega balance", prop["dha"], prop["epa"], a_idx, b_idx,
                            "Docosahexaenoic (22:6) / EPA (20:5) feature ratio",
                            "Higher DHA relative to EPA in B", "Lower DHA/EPA in B"))
    raw.append(_ratio_index("Omega-3 index", "Omega balance", prop["n3"], total, a_idx, b_idx,
                            "n3-feature intensity / total (approx. 18:3/20:5/22:6)",
                            "Higher n3 content in B", "Lower n3 content in B"))
    raw.append(_ratio_index("n3/n6", "Omega balance", prop["n3"], prop["n6"], a_idx, b_idx,
                            "Omega-3 / omega-6 feature ratio",
                            "Higher n3/n6 balance in B", "Lower n3/n6 balance in B"))
    raw.append(_ratio_index("Plasmalogen fraction", "Ether-linked chains", prop["plasmalogen"], total, a_idx, b_idx,
                            "Plasmalogen-feature intensity / total",
                            "Higher plasmalogen (antioxidant ether lipids) in B", "Lower plasmalogens in B"))
    raw.append(_ratio_index("Alkenyl chain fraction", "Ether-linked chains", prop["plasmalogen"], prop["ether"], a_idx, b_idx,
                            "Plasmalogen / total ether-linked features",
                            "Higher alkenyl-chain lipids in B", "Lower alkenyl-chain lipids in B"))

    # Nutritional quality indices
    raw.append(_ratio_index("Atherogenicity index (AI)", "Nutritional quality", prop["c12_0"] + 4 * prop["c14_0"] + prop["c16_0"],
                            prop["monounsat"] + prop["polyunsat"], a_idx, b_idx,
                            "(12:0 + 4×14:0 + 16:0) / (MUFA + PUFA)",
                            "Higher atherogenic potential in B", "Lower AI in B"))
    n3_n6_ratio = _safe_div(prop["n3"], prop["n6"], 0.0)
    ti_den = 0.5 * prop["monounsat"] + 0.5 * prop["n6"] + 3 * prop["n3"] + n3_n6_ratio
    raw.append(_ratio_index("Thrombogenicity index (TI)", "Nutritional quality", prop["c14_0"] + prop["c16_0"] + prop["c18_0"],
                            ti_den, a_idx, b_idx,
                            "(14:0 + 16:0 + 18:0) / (0.5MUFA + 0.5n6 + 3n3 + n3/n6)",
                            "Higher thrombogenic potential in B", "Lower TI in B"))
    raw.append(_ratio_index("h/H ratio", "Nutritional quality", prop["c18_1"] + prop["c16_1"] + prop["polyunsat"],
                            prop["c14_0"] + prop["c16_0"], a_idx, b_idx,
                            "(C16:1 + C18:1 + PUFA) / (C14:0 + C16:0)",
                            "Higher hypocholesterolemic potential in B", "Lower h/H in B"))
    raw.append(_ratio_index("EPA fraction", "Nutritional quality", prop["c20_5"], total, a_idx, b_idx,
                            "EPA (20:5n3) feature intensity / total",
                            "Higher EPA content in B", "Lower EPA fraction in B"))
    raw.append(_ratio_index("DHA fraction", "Nutritional quality", prop["c22_6"], total, a_idx, b_idx,
                            "DHA (22:6n3) feature intensity / total",
                            "Higher DHA content in B", "Lower DHA fraction in B"))
    raw.append(_ratio_index("n6 fraction", "Nutritional quality", prop["n6"], total, a_idx, b_idx,
                            "Omega-6 feature intensity / total",
                            "Higher n6 content in B", "Lower n6 fraction in B"))
    raw.append(_ratio_index("PUFA/MUFA", "Nutritional quality", prop["polyunsat"], prop["monounsat"], a_idx, b_idx,
                            "Polyunsaturated / monounsaturated balance",
                            "Higher PUFA relative to MUFA in B", "Lower PUFA/MUFA in B"))

    pvals = [r["pvalue"] for r in raw]
    padjs = _bh(pvals)
    for r, p in zip(raw, padjs):
        r["padj"] = p
    _label_interpretations(raw, group_a, group_b)
    return raw
