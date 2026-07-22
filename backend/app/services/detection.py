import os
import re
from typing import Any, Dict, List, Tuple
import pandas as pd


KNOWN_FORMATS = {
    "compound_discoverer": ["Name", "Formula", "m/z", "Retention Time", "Area"],
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


def _normalize_lipidsearch_sample_id(sample_id: str) -> str:
    """Convert 's01-1' -> 's1-1' to match alignment file sample ids."""
    if not sample_id:
        return sample_id
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", sample_id.lower())


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
            # group prefix is the sample id without replicate suffix
            group = sid.split("-")[0]
            sample_groups[col] = group

    return chosen, sample_groups, candidates


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


def detect_columns(df: pd.DataFrame, alignment: Dict[str, str] = None) -> Dict[str, Any]:
    columns = [str(c) for c in df.columns]

    feature_markers = {
        "feature_id": ["name", "compound", "lipidion", "lipid ion", "metabolite", "lipidmolec"],
        "formula": ["formula", "molecular formula"],
        "mz": ["m/z", "precursor mz", "precursor_mz", "calcmass"],
        "rt": ["retention time", "retentiontime", "rt (min)", "rt", "basert"],
        "adduct": ["adduct", "ion type", "ion_type"],
        "lipid_class": ["lipid class", "lipid_class", "class", "classkey"],
        "grade": ["grade", "score", "totalgrade"],
        "fa": ["fa", "fatty acyl", "fattyacid", "fa composition", "fakey"],
    }
    suggested = {}
    already = set()
    for key, markers in feature_markers.items():
        for col in columns:
            col_lower = col.lower()
            if any(col_lower == m or col_lower.startswith(m + " ") or col_lower.endswith(" " + m) for m in markers):
                if col not in already:
                    suggested[key] = col
                    already.add(col)
                    break

    # Try LipidSearch-specific area columns first
    lipidsearch_samples, lipidsearch_groups, lipidsearch_candidates = _detect_lipidsearch_samples(columns)

    if lipidsearch_samples:
        sample_columns = lipidsearch_samples
        sample_groups = lipidsearch_groups
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

    # Apply alignment file mapping if provided (maps normalized sample id to group name)
    if alignment:
        for col in sample_columns:
            m = LIPIDSEARCH_AREA_RE.match(str(col))
            if m:
                sid = _normalize_lipidsearch_sample_id(m.group("sample"))
                if sid in alignment:
                    sample_groups[col] = alignment[sid]
            elif col in alignment:
                sample_groups[col] = alignment[col]

    feature_columns = [c for c in columns if c not in sample_columns and c not in already]
    return {
        "suggested_mapping": suggested,
        "sample_columns": sample_columns,
        "feature_columns": feature_columns,
        "sample_groups": sample_groups,
        "lipidsearch_candidates": lipidsearch_candidates,
    }


def parse_lipidsearch_alignment(path: str) -> Dict[str, str]:
    """Parse a LipidSearch alignment .txt file and return sample_id -> group_name mapping."""
    mapping = {}
    if not os.path.exists(path):
        return mapping

    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        in_section = False
        for raw_line in fh:
            # Strip line endings but preserve internal tabs
            line = raw_line.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
            if not line:
                continue
            if line.startswith("*Target search job"):
                in_section = True
                continue
            if in_section:
                # Next section header ends the target search job block
                if line.startswith("*"):
                    break
                parts = line.split("\t")
                if len(parts) >= 4:
                    sid = _normalize_lipidsearch_sample_id(parts[2].strip())
                    mapping[sid] = parts[3].strip()
    return mapping


def preview_file(uploaded, sheet: str = None, alignment: Dict[str, str] = None) -> Dict[str, Any]:
    path = os.path.join("uploads", uploaded.stored_name)
    df = read_file_to_df(path, sheet)
    mapping = detect_columns(df, alignment=alignment)
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
