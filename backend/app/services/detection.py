import os
import re
from typing import Any, Dict, List
import pandas as pd


KNOWN_FORMATS = {
    "compound_discoverer": ["Name", "Formula", "m/z", "Retention Time", "Area"],
    "lipidsearch": ["LipidIon", "Class", "FA", "Grade", "Rt", "Area"],
}

SAMPLE_REGEX = re.compile(r"area|intensity|abundance|sample|ctrl|control|treat|rep|replicate|_[0-9]+$", re.I)
GROUP_REGEX = re.compile(r"^(?P<group>.+?)_(?P<idx>[0-9]+)$")


def read_file_to_df(path: str, sheet: str = None) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        if sheet:
            return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        return pd.read_excel(path, engine="openpyxl")
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    if ext in [".tsv", ".txt"]:
        return pd.read_csv(path, sep="\t", low_memory=False)
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


def detect_columns(df: pd.DataFrame) -> Dict[str, Any]:
    columns = [str(c) for c in df.columns]

    feature_markers = {
        "feature_id": ["name", "compound", "lipidion", "lipid ion", "metabolite"],
        "formula": ["formula", "molecular formula"],
        "mz": ["m/z", "precursor mz", "precursor_mz"],
        "rt": ["retention time", "retentiontime", "rt (min)", "rt"],
        "adduct": ["adduct", "ion type", "ion_type"],
        "lipid_class": ["lipid class", "lipid_class", "class"],
        "grade": ["grade", "score"],
        "fa": ["fa", "fatty acyl", "fattyacid", "fa composition"],
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

    feature_columns = [c for c in columns if c not in sample_columns and c not in already]
    return {
        "suggested_mapping": suggested,
        "sample_columns": sample_columns,
        "feature_columns": feature_columns,
        "sample_groups": sample_groups,
    }


def preview_file(uploaded, sheet: str = None) -> Dict[str, Any]:
    path = os.path.join("uploads", uploaded.stored_name)
    df = read_file_to_df(path, sheet)
    mapping = detect_columns(df)
    return {
        "detected_format": uploaded.detected_format,
        "sheets": list_sheets(path),
        "columns": [str(c) for c in df.columns],
        "sample_columns": mapping["sample_columns"],
        "feature_columns": mapping["feature_columns"],
        "row_count": len(df),
        "suggested_mapping": mapping["suggested_mapping"],
        "sample_groups": mapping["sample_groups"],
    }
