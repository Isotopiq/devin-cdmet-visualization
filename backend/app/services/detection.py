import os
import re
from typing import Any, Dict, List, Tuple
import pandas as pd


KNOWN_FORMATS = {
    "compound_discoverer": ["Name", "Formula", "m/z", "RT", "Area"],
    "lipidsearch": ["LipidMolec", "ClassKey", "FAKey", "CalcMass", "BaseRt", "TotalGrade", "Area"],
}

SAMPLE_REGEX = re.compile(r"area|intensity|abundance|sample|ctrl|control|treat|rep|replicate|_[0-9]+$", re.I)
GROUP_REGEX = re.compile(r"^(?P<group>.+?)_(?P<idx>[0-9]+)$")

# LipidSearch 5.x bracketed area columns, e.g. OrgMeanArea[s01], NormArea[s01-1]
LIPIDSEARCH_AREA_RE = re.compile(
    r"^(?P<type>OrgMeanArea|NormArea|OriginalArea|NormHeight|OriginalHeight|Conc)"
    r"\[(?P<sample>s?\d+(?:-\d+)?)\]$",
    re.I,
)

# Compound Discoverer area columns, e.g. "Area: EL-008.raw (F26)"
COMPOUND_DISCOVERER_AREA_RE = re.compile(
    r"^Area:\s*(?P<raw>.+?)\s*\((?P<filecode>F\d+)\)\s*$",
    re.I,
)


def _normalize_lipidsearch_sample_id(sample_id: str) -> str:
    """Convert 's01-1' -> 's1-1' to match alignment file sample ids."""
    if not sample_id:
        return sample_id
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", sample_id.lower())


def _base_raw_name(raw: str) -> str:
    """Strip common raw-file extensions from a Compound Discoverer raw name."""
    name = str(raw).strip()
    for ext in [".raw", "_raw"]:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
    return name


def _detect_lipidsearch_samples(columns: List[str]) -> Tuple[List[str], Dict[str, str], Dict[str, List[str]]]:
    """Return preferred sample columns, sample groups, and all candidate intensity sets for LipidSearch exports."""
    candidates: Dict[str, List[str]] = {}
    for col in columns:
        m = LIPIDSEARCH_AREA_RE.match(str(col))
        if m:
            intensity_type = m.group("type").lower()
            candidates.setdefault(intensity_type, []).append(col)

    # Preferred order: normalized area per replicate, then original area, then mean area, then conc
    priority = ["normarea", "originalarea", "orgmeanarea", "conc"]
    chosen = []
    for itype in priority:
        if itype in candidates:
            chosen = candidates[itype]
            break

    sample_groups = {}
    for col in chosen:
        m = LIPIDSEARCH_AREA_RE.match(str(col))
        if m:
            sid = _normalize_lipidsearch_sample_id(m.group("sample"))
            group = sid.split("-")[0]
            sample_groups[col] = group

    return chosen, sample_groups, candidates


def _detect_compound_discoverer_samples(columns: List[str], metadata: Dict[str, Dict[str, Any]]) -> Tuple[List[str], Dict[str, str]]:
    """Detect Compound Discoverer sample area columns and apply metadata mapping."""
    sample_columns = []
    sample_groups = {}
    for col in columns:
        m = COMPOUND_DISCOVERER_AREA_RE.match(str(col))
        if m:
            sample_columns.append(col)
            filecode = m.group("filecode").upper()
            raw_base = _base_raw_name(m.group("raw"))
            if metadata and filecode in metadata:
                sample_groups[col] = metadata[filecode].get("condition", raw_base)
            elif metadata and raw_base.lower() in metadata:
                sample_groups[col] = metadata[raw_base.lower()].get("condition", raw_base)
            else:
                sample_groups[col] = raw_base
    return sample_columns, sample_groups


def read_file_to_df(path: str, sheet: str = None) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        if sheet:
            return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        return pd.read_excel(path, engine="openpyxl")
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    if ext in [".tsv", ".txt"]:
        return pd.read_csv(path, sep="\t", low_memory=False, encoding="utf-8")
    raise ValueError(f"Unsupported file extension: {ext}")


def list_sheets(path: str) -> List[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(path, engine="openpyxl")
        return xl.sheet_names
    return []


def detect_file_format(path: str, ext: str = None) -> Dict[str, Any]:
    ext = ext or os.path.splitext(path)[1].lower()
    try:
        sheets = list_sheets(path)
        if sheets:
            df = pd.read_excel(path, sheet_name=sheets[0], engine="openpyxl", nrows=5)
        else:
            if ext == ".csv":
                df = pd.read_csv(path, nrows=5, low_memory=False)
            else:
                df = pd.read_csv(path, sep="\t", nrows=5, low_memory=False)
    except Exception as e:
        return {"format": None, "error": str(e), "sheets": []}

    columns = [str(c) for c in df.columns]
    scores = {}
    for fmt, markers in KNOWN_FORMATS.items():
        scores[fmt] = sum(1 for m in markers if any(m.lower() in c.lower() for c in columns))
    best = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else None
    return {"format": best, "scores": scores, "sheets": sheets, "columns": columns}


def detect_columns(df: pd.DataFrame, metadata: Dict[str, Dict[str, Any]] = None) -> Dict[str, Any]:
    columns = [str(c) for c in df.columns]

    feature_markers = {
        "feature_id": ["name", "compound", "lipidion", "lipid ion", "metabolite", "lipidmolec"],
        "formula": ["formula", "molecular formula"],
        "mz": ["m/z", "precursor mz", "precursor_mz", "calcmass"],
        "rt": ["retention time", "retentiontime", "rt (min)", "rt [min]", "rt", "basert"],
        "adduct": ["adduct", "reference ion", "ion type", "ion_type"],
        "lipid_class": ["lipid class", "lipid_class", "classkey"],
        "grade": ["grade", "score", "totalgrade"],
        "fa": ["fa", "fatty acyl", "fattyacid", "fa composition", "fakey"],
        "calc_mw": ["calc. mw", "calc.mw", "calculated mw"],
        "polarity": ["polarity"],
        "neutral_losses": ["neutral losses", "neutral_losses"],
    }
    suggested = {}
    already = set()
    for key, markers in feature_markers.items():
        for col in columns:
            col_lower = col.lower()
            if key == "lipid_class":
                # avoid CD "Class Coverage", "Class FISh Score" columns
                if any(w in col_lower for w in ["coverage", "fish", "score"]):
                    continue
            if any(
                col_lower == m
                or col_lower.startswith(m + " ")
                or col_lower.endswith(" " + m)
                or (m in col_lower and "(" + m + ")" in col_lower)
                for m in markers
            ):
                if col not in already:
                    suggested[key] = col
                    already.add(col)
                    break

    # Try Compound Discoverer-specific area columns first
    cd_samples, cd_groups = _detect_compound_discoverer_samples(columns, metadata or {})

    # Try LipidSearch-specific area columns next
    ls_samples, ls_groups, ls_candidates = _detect_lipidsearch_samples(columns)

    if cd_samples:
        sample_columns = cd_samples
        sample_groups = cd_groups
    elif ls_samples:
        sample_columns = ls_samples
        sample_groups = ls_groups
    else:
        sample_columns = [c for c in columns if SAMPLE_REGEX.search(str(c)) and c not in already]
        if not sample_columns:
            sample_columns = [c for c in columns if re.search(r"_[0-9]+$", str(c))]

        sample_groups = {}
        for col in sample_columns:
            match = GROUP_REGEX.match(str(col))
            if match:
                sample_groups[col] = match.group("group")
            else:
                sample_groups[col] = "unknown"

    # Apply LipidSearch alignment file mapping if metadata was supplied that way
    if metadata:
        for col in sample_columns:
            m = LIPIDSEARCH_AREA_RE.match(str(col))
            if m:
                sid = _normalize_lipidsearch_sample_id(m.group("sample"))
                if sid in metadata:
                    sample_groups[col] = metadata[sid].get("condition", sample_groups[col])
            elif col in metadata:
                sample_groups[col] = metadata[col].get("condition", sample_groups[col])

    feature_columns = [c for c in columns if c not in sample_columns and c not in already]
    return {
        "suggested_mapping": suggested,
        "sample_columns": sample_columns,
        "feature_columns": feature_columns,
        "sample_groups": sample_groups,
        "lipidsearch_candidates": ls_candidates,
    }


def parse_lipidsearch_alignment(path: str) -> Dict[str, Dict[str, Any]]:
    """Parse a LipidSearch alignment .txt file and return sample_id -> {condition} mapping."""
    mapping: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(path):
        return mapping

    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        in_section = False
        for raw_line in fh:
            line = raw_line.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
            if not line:
                continue
            if line.startswith("*Target search job"):
                in_section = True
                continue
            if in_section:
                if line.startswith("*"):
                    break
                parts = line.split("\t")
                if len(parts) >= 4:
                    sid = _normalize_lipidsearch_sample_id(parts[2].strip())
                    mapping[sid] = {"condition": parts[3].strip()}
    return mapping


def parse_compound_discoverer_metadata(path: str) -> Dict[str, Dict[str, Any]]:
    """Parse a Compound Discoverer metadata .xlsx/.csv/.txt and return file identifier -> metadata mapping."""
    mapping: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(path):
        return mapping

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in [".xlsx", ".xls"]:
            xl = pd.ExcelFile(path, engine="openpyxl")
            df = pd.read_excel(path, sheet_name=xl.sheet_names[0])
        elif ext == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_csv(path, sep="\t")
    except Exception:
        return mapping

    for _, row in df.iterrows():
        def _get(col):
            val = row.get(col, "")
            if pd.isna(val):
                return ""
            return str(val).strip()

        sample = _get("Sample")
        file_code = _get("File").upper()
        sample_id = _get("Sample Identifier")
        sample_type = _get("Sample Type")
        condition = _get("Condition")

        meta = {
            "sample": sample,
            "file_code": file_code,
            "sample_identifier": sample_id,
            "sample_type": sample_type,
            "condition": condition or sample_type or sample_id,
        }
        if file_code:
            mapping[file_code] = meta
        if sample_id:
            mapping[_base_raw_name(sample_id).lower()] = meta
            mapping[sample_id.lower()] = meta
        if sample:
            mapping[sample.upper()] = meta
    return mapping


def parse_sample_metadata(path: str) -> Dict[str, Dict[str, Any]]:
    """Dispatch to the correct metadata/alignment parser based on file content."""
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls", ".csv"]:
        # Try CD metadata first; if empty, fall back to generic
        mapping = parse_compound_discoverer_metadata(path)
        if mapping:
            return mapping
    if ext in [".txt", ".tsv", ".csv"]:
        mapping = parse_lipidsearch_alignment(path)
        if mapping:
            return mapping
    return {}


def preview_file(uploaded, sheet: str = None, metadata: Dict[str, Dict[str, Any]] = None) -> Dict[str, Any]:
    path = os.path.join("uploads", uploaded.stored_name)
    df = read_file_to_df(path, sheet)
    mapping = detect_columns(df, metadata=metadata)
    return {
        "detected_format": uploaded.detected_format,
        "sheets": list_sheets(path),
        "columns": [str(c) for c in df.columns],
        "sample_columns": mapping["sample_columns"],
        "feature_columns": mapping["feature_columns"],
        "row_count": len(df),
        "suggested_mapping": mapping["suggested_mapping"],
        "sample_groups": mapping["sample_groups"],
        "lipidsearch_candidates": mapping.get("lipidsearch_candidates", {}),
    }
