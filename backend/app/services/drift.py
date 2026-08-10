import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import HTTPException
from scipy.interpolate import UnivariateSpline, interp1d
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from statsmodels.nonparametric.smoothers_lowess import lowess

from app import models
from app.services.storage import get_file_path

logger = logging.getLogger(__name__)


QC_POOL_GROUP_PATTERNS = [
    r"qc[-_\s]*pool|pool[-_\s]*qc|pooled[-_\s]*qc|quality[-_\s]*control[-_\s]*pool|pooled[-_\s]*quality[-_\s]*control",
]
QC_FALLBACK_PATTERNS = [
    r"\bqc\b|quality[-_\s]*control",
    r"pooled",
]


def _positive_floor(df: pd.DataFrame) -> float:
    """Return a small positive value based on the smallest positive value in df."""
    pos = df.values[df.values > 0]
    if pos.size == 0:
        return 1e-12
    return float(np.nanmin(pos)) / 2


def _normalised_group_name(group: Any) -> str:
    return str(group).strip().lower()


def auto_detect_qc_pool_group(sample_metadata: Dict[str, Any]) -> Optional[str]:
    """Auto-detect the QC-Pool group from sample metadata.

    Prefers group names that contain both a QC term and a pool term. Falls back
    to any QC group or any pooled group. Returns the matching group with the
    most samples.
    """
    group_counts: Dict[str, int] = {}
    for sample, group in sample_metadata.items():
        group_counts[str(group)] = group_counts.get(str(group), 0) + 1

    for patterns in (QC_POOL_GROUP_PATTERNS, QC_FALLBACK_PATTERNS):
        for pattern in patterns:
            matches = {
                g: c
                for g, c in group_counts.items()
                if re.search(pattern, _normalised_group_name(g), re.IGNORECASE)
            }
            if matches:
                return max(matches.items(), key=lambda x: x[1])[0]
    return None


def _qc_pool_columns(
    df: pd.DataFrame,
    sample_metadata: Dict[str, Any],
    qc_pool_group: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Return the list of QC-Pool sample columns and the group used.

    If ``qc_pool_group`` is not provided, auto-detect it. Raises if none found.
    """
    if not qc_pool_group:
        qc_pool_group = auto_detect_qc_pool_group(sample_metadata)
    if not qc_pool_group:
        raise HTTPException(
            status_code=400,
            detail="No QC-Pool group detected. Please assign a QC-Pool group in the sample metadata or select one manually.",
        )
    qc_cols = [c for c in df.columns if str(sample_metadata.get(c, "")) == str(qc_pool_group)]
    if not qc_cols:
        raise HTTPException(
            status_code=400,
            detail=f"No samples found for QC-Pool group '{qc_pool_group}'. Please check the group assignment.",
        )
    return qc_cols, qc_pool_group


def _run_order_map(
    df: pd.DataFrame,
    run_order: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    """Build a run-order map for all columns.

    If ``run_order`` is provided, missing columns are appended with the next
    available integer. If not provided, column order is used.
    """
    cols = list(df.columns)
    if not run_order:
        return {c: i for i, c in enumerate(cols)}
    mapping = {k: v for k, v in run_order.items() if k in cols}
    used = set(mapping.values())
    next_order = max(used, default=-1) + 1
    for c in cols:
        if c not in mapping:
            while next_order in used:
                next_order += 1
            mapping[c] = next_order
            used.add(next_order)
            next_order += 1
    return mapping


async def load_run_order_file(
    db: AsyncSession,
    file_id: int,
    sample_columns: List[str],
) -> Dict[str, int]:
    """Load a sample -> run order mapping from an uploaded CSV/Excel file.

    Expected columns: 'sample' or 'sample_name' and 'order', 'run_order' or 'position'.
    Any samples not in the file are assigned the next available integer.
    """
    result = await db.execute(
        select(models.UploadedFile).where(models.UploadedFile.id == file_id)
    )
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=400, detail=f"Run-order file not found: {file_id}")

    path = str(await get_file_path(uploaded.stored_name, db))
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        df = pd.read_csv(path, sep=None, engine="python")

    if df.empty:
        raise HTTPException(status_code=400, detail="Run-order file is empty")

    sample_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("sample", "sample_name", "sample id", "sample_id", "sampleid"):
            sample_col = c
            break
    if sample_col is None:
        sample_col = df.columns[0]

    order_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("order", "run_order", "run order", "position", "index"):
            order_col = c
            break
    if order_col is None:
        order_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

    df[order_col] = pd.to_numeric(df[order_col], errors="coerce")
    df = df.dropna(subset=[order_col])

    mapping: Dict[str, int] = {}
    for _, row in df.iterrows():
        sample = str(row[sample_col]).strip()
        if sample:
            mapping[sample] = int(row[order_col])

    missing = [c for c in sample_columns if c not in mapping]
    if missing:
        next_order = max(mapping.values(), default=-1) + 1
        for c in missing:
            mapping[c] = next_order
            next_order += 1
    return mapping


def _prepare_values(values: np.ndarray, space: str, floor: float) -> np.ndarray:
    """Return a finite, positive array and its transformed representation for fitting."""
    y = np.where(np.isfinite(values) & (values > 0), values, floor)
    if space == "log":
        return np.log2(y)
    return y


def _fit_lowess(
    x: np.ndarray,
    y: np.ndarray,
    span: float,
) -> np.ndarray:
    """Fit LOWESS and return fitted values at the input x positions."""
    order = np.argsort(x)
    x_sorted = x[order]
    y_sorted = y[order]
    try:
        fitted_sorted = lowess(
            y_sorted,
            x_sorted,
            frac=span,
            it=3,
            is_sorted=True,
            return_sorted=False,
        )
    except Exception as _exc:
        logger.exception("LOWESS fit failed; falling back to linear regression")
        fitted_sorted = _fit_linear(x_sorted, y_sorted)
    fitted = np.empty_like(fitted_sorted)
    fitted[order] = fitted_sorted
    return fitted


def _fit_linear(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit a line through QC points and return fitted y at those x values."""
    if len(x) == 1:
        return np.full_like(y, y[0])
    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return np.full_like(y, np.median(y))
    return slope * x + intercept


def _fit_spline(x: np.ndarray, y: np.ndarray, smoothing: Optional[float] = None) -> np.ndarray:
    """Fit a smoothing spline and return fitted values at the input x positions."""
    if len(x) < 4:
        return _fit_linear(x, y)
    if smoothing is None:
        smoothing = float(len(x)) * 0.01
    try:
        spl = UnivariateSpline(x, y, s=smoothing)
        return spl(x)
    except Exception as _exc:
        logger.exception("Spline fit failed; falling back to linear regression")
        return _fit_linear(x, y)


def _predict_at_positions(
    x_qc: np.ndarray,
    y_fit_qc: np.ndarray,
    positions: np.ndarray,
    extrapolate: str,
) -> np.ndarray:
    """Predict fitted values at arbitrary positions by interpolating between QC fits."""
    order = np.argsort(x_qc)
    x_sorted = x_qc[order]
    y_sorted = y_fit_qc[order]

    if extrapolate == "last":
        predicted = np.interp(positions, x_sorted, y_sorted, left=y_sorted[0], right=y_sorted[-1])
    elif extrapolate == "linear":
        if len(x_sorted) >= 2:
            left_slope = (y_sorted[1] - y_sorted[0]) / max(1e-9, x_sorted[1] - x_sorted[0])
            right_slope = (y_sorted[-1] - y_sorted[-2]) / max(1e-9, x_sorted[-1] - x_sorted[-2])
            left_val = y_sorted[0] + left_slope * (positions - x_sorted[0])
            right_val = y_sorted[-1] + right_slope * (positions - x_sorted[-1])
        else:
            left_val = y_sorted[0]
            right_val = y_sorted[0]
        predicted = np.where(
            positions < x_sorted[0],
            left_val,
            np.where(positions > x_sorted[-1], right_val, np.interp(positions, x_sorted, y_sorted)),
        )
    else:  # "none" / flat nearest
        predicted = np.interp(positions, x_sorted, y_sorted, left=y_sorted[0], right=y_sorted[-1])
    return predicted


def _target_value(qc_values: np.ndarray, target: str, x_qc: np.ndarray) -> float:
    """Return the reference level from a set of QC values.

    ``target`` is one of mean, median, first (smallest run order) or last.
    """
    if target == "mean":
        return float(np.mean(qc_values))
    if target in ("first", "last"):
        if len(x_qc) == 0:
            return float(np.median(qc_values))
        order = np.argsort(x_qc)
        idx = order[0] if target == "first" else order[-1]
        return float(qc_values[idx])
    return float(np.median(qc_values))


def _global_tic_correction(
    df: pd.DataFrame,
    qc_cols: List[str],
    order_map: Dict[str, int],
    method: str,
    space: str,
    span: float,
    target: str,
    extrapolate: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Correct drift using the total ion current (TIC) of QC-Pool samples."""
    floor = _positive_floor(df)
    all_cols = list(df.columns)
    positions = np.array([order_map[c] for c in all_cols], dtype=float)
    qc_positions = np.array([order_map[c] for c in qc_cols], dtype=float)

    tic = df[qc_cols].sum(axis=0).to_numpy(dtype=float)
    y = _prepare_values(tic, space, floor)

    all_tic = df.sum(axis=0).to_numpy(dtype=float)
    all_y = _prepare_values(all_tic, space, floor)

    if method == "median":
        # Simple QC-based normalization to a target statistic (no run-order trend).
        target_level = _target_value(y, target, qc_positions)
        predicted = all_y
        y_fit_qc = np.full_like(y, target_level)
    else:
        y_fit_qc = _fit_qc_trend(qc_positions, y, method, span)
        target_level = _target_value(y_fit_qc, target, qc_positions)
        predicted = _predict_at_positions(qc_positions, y_fit_qc, positions, extrapolate)

    if space == "log":
        scale_log = target_level - predicted
        scale = 2.0 ** scale_log
    else:
        predicted = np.where(predicted <= 0, floor, predicted)
        scale = target_level / predicted

    corrected = df.copy()
    for i, col in enumerate(all_cols):
        corrected[col] = df[col] * scale[i]

    diagnostics = {
        "qc_pool_group": qc_cols,
        "method": method,
        "space": space,
        "target": target,
        "extrapolate": extrapolate,
        "qc_positions": qc_positions.tolist(),
        "qc_tic": tic.tolist(),
        "qc_tic_fitted": (2.0 ** y_fit_qc if space == "log" else y_fit_qc).tolist(),
        "sample_positions": positions.tolist(),
        "sample_scale_factors": scale.tolist(),
        "sample_tic_before": all_tic.tolist(),
        "sample_tic_after": corrected.sum(axis=0).to_numpy().tolist(),
    }
    return corrected, diagnostics


def _fit_qc_trend(
    x: np.ndarray,
    y: np.ndarray,
    method: str,
    span: float,
) -> np.ndarray:
    """Fit the QC trend for a single variable (already transformed if needed)."""
    if method == "median":
        return np.full_like(y, np.median(y))
    if method == "linear":
        return _fit_linear(x, y)
    if method == "loess":
        return _fit_lowess(x, y, span)
    if method == "spline":
        return _fit_spline(x, y)
    raise HTTPException(status_code=400, detail=f"Unknown QC drift method: {method}")


def _per_feature_correction(
    df: pd.DataFrame,
    qc_cols: List[str],
    order_map: Dict[str, int],
    method: str,
    space: str,
    span: float,
    target: str,
    extrapolate: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Correct drift independently for each feature using QC-Pool values."""
    floor = _positive_floor(df)
    all_cols = list(df.columns)
    positions = np.array([order_map[c] for c in all_cols], dtype=float)
    qc_positions = np.array([order_map[c] for c in qc_cols], dtype=float)

    corrected = df.copy()
    feature_diagnostics: List[Dict[str, Any]] = []

    for feature in df.index:
        values = df.loc[feature, qc_cols].to_numpy(dtype=float)
        all_values = df.loc[feature, all_cols].to_numpy(dtype=float)
        y = _prepare_values(values, space, floor)
        all_y = _prepare_values(all_values, space, floor)

        if method == "median":
            target_level = _target_value(y, target, qc_positions)
            y_fit_qc = np.full_like(y, target_level)
            predicted = all_y
        else:
            y_fit_qc = _fit_qc_trend(qc_positions, y, method, span)
            target_level = _target_value(y_fit_qc, target, qc_positions)
            predicted = _predict_at_positions(qc_positions, y_fit_qc, positions, extrapolate)

        if space == "log":
            scale_log = target_level - predicted
            scale = 2.0 ** scale_log
        else:
            predicted = np.where(predicted <= 0, floor, predicted)
            scale = target_level / predicted

        corrected.loc[feature, all_cols] = all_values * scale

        feature_diagnostics.append({
            "feature": str(feature),
            "qc_values": values.tolist(),
            "qc_fitted": (2.0 ** y_fit_qc if space == "log" else y_fit_qc).tolist(),
            "scale_factors": scale.tolist(),
        })

    diagnostics = {
        "qc_pool_group": qc_cols,
        "method": method,
        "space": space,
        "target": target,
        "extrapolate": extrapolate,
        "feature_count": len(df.index),
        "qc_positions": qc_positions.tolist(),
        "sample_positions": positions.tolist(),
        "features": feature_diagnostics[:5],  # summarise first few to avoid huge payloads
    }
    return corrected, diagnostics


def _method_name(method: str, level: str) -> str:
    """Return the base method name and whether it is per-feature."""
    method_lower = method.lower().replace(" ", "_")
    if method_lower.startswith("median_"):
        return "median", level == "feature"
    if method_lower.startswith("linear_"):
        return "linear", level == "feature"
    if method_lower.startswith("loess_"):
        return "loess", level == "feature"
    if method_lower.startswith("spline_"):
        return "spline", level == "feature"
    # default to TIC loess if unrecognised
    return "loess", False


def correct_qc_pool_drift(
    df: pd.DataFrame,
    sample_metadata: Dict[str, Any],
    params: Any,
    run_order: Optional[Dict[str, int]] = None,
    batch_labels: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Apply QC-Pool drift correction to a DataFrame.

    ``params`` may be a Pydantic model or any object with the expected attributes.
    ``batch_labels`` is an optional sample -> batch map; if provided, the fit is done
    independently per batch.
    """
    import inspect

    def _get(name: str, default: Any = None) -> Any:
        if hasattr(params, name):
            return getattr(params, name)
        if isinstance(params, dict):
            return params.get(name, default)
        return default

    qc_pool_group = _get("qc_pool_group") or None
    method = _get("qc_pool_method", "loess_tic")
    space = _get("qc_pool_space", "log")
    span = float(_get("qc_pool_span", 0.75))
    target = _get("qc_pool_target", "median")
    extrapolate = _get("qc_pool_extrapolate", "last")

    if method.endswith("_per_feature"):
        level = "feature"
        base = method.replace("_per_feature", "")
    elif method.endswith("_tic"):
        level = "tic"
        base = method.replace("_tic", "")
    else:
        # allow "loess", "linear", "spline", "median" as short names and default to TIC
        level = "tic"
        base = method

    valid_methods = {"median", "linear", "loess", "spline"}
    if base not in valid_methods:
        raise HTTPException(status_code=400, detail=f"Unknown QC drift method base: {base}. Choose from {sorted(valid_methods)}")

    all_cols = list(df.columns)
    order_map = _run_order_map(df, run_order)

    if batch_labels:
        batches = sorted(set(batch_labels.values()))
        corrected = df.copy()
        diagnostics = {"batches": {}}
        for batch in batches:
            batch_cols = [c for c in all_cols if batch_labels.get(c) == batch]
            batch_qc_cols = [c for c in batch_cols if str(sample_metadata.get(c, "")) == str(qc_pool_group)]
            if not batch_qc_cols:
                logger.warning("No QC-Pool samples found in batch %s; skipping", batch)
                continue
            batch_df = df[batch_cols]
            batch_meta = {c: sample_metadata[c] for c in batch_cols if c in sample_metadata}
            batch_order = {c: order_map[c] for c in batch_cols}
            batch_corrected, batch_diag = _apply_single_batch(
                batch_df,
                batch_meta,
                batch_qc_cols,
                batch_order,
                base,
                level,
                space,
                span,
                target,
                extrapolate,
            )
            corrected[batch_cols] = batch_corrected[batch_cols]
            diagnostics["batches"][batch] = batch_diag
        return corrected, diagnostics

    return _apply_single_batch(
        df,
        sample_metadata,
        None,
        order_map,
        base,
        level,
        space,
        span,
        target,
        extrapolate,
        qc_pool_group=qc_pool_group,
    )


def _apply_single_batch(
    df: pd.DataFrame,
    sample_metadata: Dict[str, Any],
    qc_cols_override: Optional[List[str]],
    order_map: Dict[str, int],
    base: str,
    level: str,
    space: str,
    span: float,
    target: str,
    extrapolate: str,
    qc_pool_group: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Apply QC-Pool drift correction to a single batch (or a whole dataset)."""
    if qc_cols_override is not None:
        qc_cols = qc_cols_override
    else:
        qc_cols, qc_pool_group = _qc_pool_columns(df, sample_metadata, qc_pool_group)

    if len(qc_cols) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"At least 2 QC-Pool samples are required for drift correction. Found {len(qc_cols)} in group '{qc_pool_group}'.",
        )

    if level == "feature":
        corrected, diagnostics = _per_feature_correction(
            df,
            qc_cols,
            order_map,
            base,
            space,
            span,
            target,
            extrapolate,
        )
    else:
        corrected, diagnostics = _global_tic_correction(
            df,
            qc_cols,
            order_map,
            base,
            space,
            span,
            target,
            extrapolate,
        )

    diagnostics["qc_pool_group_used"] = qc_pool_group
    return corrected, diagnostics
