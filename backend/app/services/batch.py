import copy
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from scipy import stats
from statsmodels.nonparametric.smoothers_lowess import lowess

from app import models
from app.services.preprocessing import _to_json_safe


VALID_BATCH_METHODS = {
    "reference_group",
    "log2fc_control",
    "mean_centering",
    "median_centering",
    "quantile_normalization",
    "combat",
    "loess_signal_drift",
    "ruv_iii_c",
}


def _positive_floor(df: pd.DataFrame) -> float:
    pos = df.values[df.values > 0]
    if pos.size == 0:
        return 1e-12
    return float(np.nanmin(pos))


def _feature_id(meta: Dict[str, Any]) -> str:
    return str(meta.get("feature_id", "")).strip()


def _unique_feature_ids(feature_metadata: List[Dict[str, Any]], dataset_id: int) -> List[str]:
    """Return a list of unique feature IDs; duplicates get a numeric suffix."""
    ids = []
    seen = {}
    for i, meta in enumerate(feature_metadata):
        fid = _feature_id(meta)
        if not fid:
            fid = f"feature_{dataset_id}_{i}"
        if fid in seen:
            seen[fid] += 1
            fid = f"{fid}_{seen[fid]}"
        else:
            seen[fid] = 0
        ids.append(fid)
    return ids


def _unique_sample_name(col: str, batch_label: str, used: set) -> str:
    col = str(col)
    batch_label = str(batch_label).strip() or "batch"
    candidate = col
    if candidate in used:
        candidate = f"{col}_{batch_label}"
    i = 2
    while candidate in used:
        candidate = f"{col}_{batch_label}_{i}"
        i += 1
    return candidate


def _build_combined_frame(
    datasets: List[models.Dataset],
    batch_assignment: Optional[Dict[str, str]],
) -> tuple[pd.DataFrame, Dict[str, str], Dict[str, str], List[Dict[str, Any]]]:
    """Return combined DataFrame, sample metadata, sample->batch map, and feature metadata."""
    batch_assignment = {int(k): v for k, v in (batch_assignment or {}).items()}
    frames: List[pd.DataFrame] = []
    sample_meta: Dict[str, str] = {}
    sample_batch: Dict[str, str] = {}
    used_samples: set = set()
    feature_meta_by_id: Dict[str, Dict[str, Any]] = {}

    for dataset in datasets:
        batch_label = (batch_assignment or {}).get(dataset.id)
        if not batch_label:
            batch_label = f"batch_{dataset.id}"
        batch_label = str(batch_label).strip() or f"batch_{dataset.id}"

        df = pd.DataFrame(dataset.data_matrix)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        feature_metadata = dataset.feature_metadata or []
        if len(feature_metadata) != len(df):
            feature_metadata = [
                {"feature_id": f"feature_{i}"} for i in range(len(df))
            ]

        fids = _unique_feature_ids(feature_metadata, dataset.id)
        df.index = fids

        # pick metadata for union of features; prefer first occurrence
        for fid, meta in zip(fids, feature_metadata):
            if fid not in feature_meta_by_id:
                feature_meta_by_id[fid] = copy.deepcopy(meta)

        # rename samples to be unique across combined dataset
        rename_map: Dict[str, str] = {}
        original_meta = dataset.sample_metadata or {}
        for raw_col in df.columns:
            new_col = _unique_sample_name(raw_col, batch_label, used_samples)
            used_samples.add(new_col)
            rename_map[raw_col] = new_col
            sample_meta[new_col] = str(original_meta.get(raw_col, "unknown"))
            sample_batch[new_col] = batch_label

        if rename_map:
            df = df.rename(columns=rename_map)
        frames.append(df)

    combined = pd.concat(frames, axis=1, join="outer", sort=False)
    combined.index = [str(i) for i in combined.index]

    # align feature metadata to combined index
    combined_feature_meta = [
        feature_meta_by_id.get(fid, {"feature_id": fid})
        for fid in combined.index
    ]
    return combined, sample_meta, sample_batch, combined_feature_meta


def _reference_control_scale(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: str,
) -> pd.DataFrame:
    """Divide each sample by the mean of the reference group within its batch."""
    result = df.copy()
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        ref_cols = [c for c in cols if sample_meta.get(c) == reference_group]
        if not ref_cols:
            continue
        ref_mean = df[ref_cols].replace(0, np.nan).mean(axis=1)
        ref_mean = ref_mean.replace(0, np.nan)
        for col in cols:
            result[col] = df[col].replace(0, np.nan).div(ref_mean)
    return result


def _log2fc_control(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: str,
) -> pd.DataFrame:
    """Convert each sample to log2 fold-change vs the batch reference group mean."""
    floor = _positive_floor(df) / 2.0
    result = df.copy()
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        ref_cols = [c for c in cols if sample_meta.get(c) == reference_group]
        if not ref_cols:
            continue
        ref_mean = df[ref_cols].replace(0, np.nan).mean(axis=1)
        ref_mean = ref_mean.replace(0, np.nan).fillna(floor)
        for col in cols:
            values = df[col].replace(0, floor).fillna(floor)
            result[col] = np.log2(values / ref_mean)
    return result


def _mean_center(df: pd.DataFrame, sample_batch: Dict[str, str]) -> pd.DataFrame:
    result = df.copy()
    global_mean = df.replace(0, np.nan).mean(axis=1)
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        if not cols:
            continue
        batch_mean = df[cols].replace(0, np.nan).mean(axis=1)
        scale = global_mean.div(batch_mean)
        scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1)
        for col in cols:
            result[col] = df[col] * scale
    return result


def _median_center(df: pd.DataFrame, sample_batch: Dict[str, str]) -> pd.DataFrame:
    result = df.copy()
    global_median = df.replace(0, np.nan).median(axis=1)
    batches = sorted(set(sample_batch.values()))
    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        if not cols:
            continue
        batch_median = df[cols].replace(0, np.nan).median(axis=1)
        scale = global_median.div(batch_median)
        scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1)
        for col in cols:
            result[col] = df[col] * scale
    return result


def _quantile_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Quantile normalize across columns (samples). NaNs and zeros are filled with a small floor."""
    floor = _positive_floor(df) / 2.0
    filled = df.replace(0, floor).fillna(floor)
    ranks = filled.apply(stats.rankdata, axis=0, method="average")
    sorted_vals = np.sort(filled.values, axis=0)
    rank_means = np.mean(sorted_vals, axis=1)
    # rankdata is 1-indexed; interpolate fractional ranks and map back to sample positions
    ranks_arr = ranks.values
    result_arr = np.interp(
        ranks_arr,
        np.arange(1, len(rank_means) + 1),
        rank_means,
    )
    result = pd.DataFrame(result_arr, index=df.index, columns=df.columns)
    # preserve original NaNs and zeros
    result = result.where(df.notna())
    result = result.where(df != 0, 0)
    return result


def _combat_empirical_bayes(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
) -> pd.DataFrame:
    """ComBat empirical Bayes batch correction.

    Adapted from brentp/combat.py (MIT). Preserves biological group differences
    by including group as a covariate in the design matrix.
    """
    import numpy.linalg as la

    # Preserve missing/zero positions; fill positive floor for the algorithm.
    floor = _positive_floor(df) / 2.0
    mask = df.isna() | (df == 0)
    data = df.copy()
    data[mask] = floor
    data = data.astype(float)

    n_features, n_samples = data.shape
    if n_samples == 0 or n_features == 0:
        return df

    # Build design matrix with batch + group covariates.
    samples = list(data.columns)
    batch = pd.Series({c: sample_batch.get(c, "unknown") for c in samples})
    group = pd.Series({c: sample_meta.get(c, "unknown") for c in samples})
    model = pd.DataFrame({"batch": batch, "group": group})

    sample_to_pos = {s: i for i, s in enumerate(samples)}
    batch_items = list(model.groupby("batch").groups.items())
    batch_levels = [k for k, v in batch_items]
    batch_info = [[sample_to_pos[s] for s in v] for k, v in batch_items]
    n_batch = len(batch_info)
    n_batches = np.array([len(v) for v in batch_info])
    n_array = float(sum(n_batches))

    if n_batch < 2:
        return df

    # One-hot encode batch and group (drop intercept-style constant columns).
    design = pd.get_dummies(model, columns=["batch", "group"], dtype=float)
    drop_cols = [c for c in design.columns if (design[c] == 1).all()]
    design = design.drop(columns=drop_cols, errors="ignore")
    if design.shape[1] == 0:
        design = pd.DataFrame({"intercept": np.ones(n_samples)}, index=samples)

    D = design.to_numpy(dtype=float)
    Y = data.to_numpy(dtype=float)

    # Standardize data.
    B_hat = la.pinv(D) @ Y.T  # shape: (design_cols, features)
    grand_mean = (n_batches / n_array) @ B_hat[:n_batch, :]
    stand_mean = np.outer(grand_mean, np.ones(n_samples))
    tmp = D.copy()
    tmp[:, :n_batch] = 0
    stand_mean += (tmp @ B_hat).T
    var_pooled = ((Y - (D @ B_hat).T) ** 2).sum(axis=1, keepdims=True) / n_array
    var_pooled = np.where(var_pooled == 0, 1e-12, var_pooled)
    s_data = (Y - stand_mean) / np.sqrt(var_pooled)

    # Fit L/S model and find priors for each batch.
    batch_design = D[:, :n_batch]
    gamma_hat = la.pinv(batch_design) @ s_data.T
    delta_hat = [s_data[:, idxs].var(axis=1) for idxs in batch_info]
    gamma_bar = gamma_hat.mean(axis=1)
    t2 = gamma_hat.var(axis=1)

    def _prior_params(m: float, s2: float):
        if s2 <= 1e-30:
            return 1e12, 1e12
        a = (2 * s2 + m**2) / s2
        b = (m * s2 + m**3) / s2
        # ComBat's inverse-gamma prior on the variance is only valid for positive b;
        # clamp to a tiny positive value to avoid pathological shrinkage.
        return max(a, 1e-12), max(b, 1e-12)

    priors = [_prior_params(m, s2) for m, s2 in zip(gamma_bar, t2)]
    a_prior = [p[0] for p in priors]
    b_prior = [p[1] for p in priors]

    def _it_sol(sdat, g_hat, d_hat, g_bar, t2_i, a, b, conv=0.0001):
        g_hat = np.asarray(g_hat, dtype=float)
        d_hat = np.asarray(d_hat, dtype=float)
        n = (1 - np.isnan(sdat)).sum(axis=1)
        g_old = g_hat.copy()
        d_old = d_hat.copy()
        g_bar = float(g_bar)
        t2_i = float(t2_i)
        a = float(a)
        b = float(b)
        change = 1.0
        while change > conv:
            g_new = (t2_i * n * g_hat + d_old * g_bar) / (t2_i * n + d_old)
            sum2 = ((sdat - np.outer(g_new, np.ones(sdat.shape[1]))) ** 2).sum(axis=1)
            d_new = (0.5 * sum2 + b) / (n / 2.0 + a - 1.0)
            d_new = np.where(d_new <= 0, 1e-12, d_new)
            change = max(
                (np.abs(g_new - g_old) / np.where(g_old == 0, 1e-12, g_old)).max(),
                (np.abs(d_new - d_old) / np.where(d_old == 0, 1e-12, d_old)).max(),
            )
            g_old = g_new
            d_old = d_new
        return g_new, d_new

    gamma_star, delta_star = [], []
    for i, batch_idxs in enumerate(batch_info):
        g, d = _it_sol(
            s_data[:, batch_idxs],
            gamma_hat[i, :],
            delta_hat[i],
            gamma_bar[i],
            t2[i],
            a_prior[i],
            b_prior[i],
        )
        gamma_star.append(g)
        delta_star.append(d)

    gamma_star = np.array(gamma_star)
    delta_star = np.array(delta_star)

    # Adjust the data.
    for j, batch_idxs in enumerate(batch_info):
        dsq = np.sqrt(delta_star[j, :]).reshape(-1, 1)
        denom = np.repeat(dsq, len(batch_idxs), axis=1)
        pred = (batch_design[batch_idxs, :] @ gamma_star).T
        s_data[:, batch_idxs] = (s_data[:, batch_idxs] - pred) / denom

    bayesdata = s_data * np.sqrt(var_pooled) + stand_mean
    result = pd.DataFrame(bayesdata, index=data.index, columns=data.columns)
    result[mask] = np.nan
    return result


def _loess_signal_drift(
    df: pd.DataFrame,
    sample_batch: Dict[str, str],
    run_order: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Correct within-batch signal drift using LOWESS on log2 total ion current (TIC).

    For each batch, the total intensity per sample is regressed against the
    acquisition/run order with LOWESS, and every feature in that sample is
    scaled by the fitted TIC trend. If ``run_order`` is not provided, the
    column order within each batch is used as the run order.
    """
    floor = _positive_floor(df) / 2.0
    result = df.copy()
    batches = sorted(set(sample_batch.values()))

    for batch in batches:
        cols = [c for c in df.columns if sample_batch.get(c) == batch]
        if not cols:
            continue
        order_map = run_order or {}
        cols_sorted = sorted(cols, key=lambda c: (order_map.get(c, cols.index(c)), c))
        x = np.array([order_map.get(c, cols.index(c)) for c in cols_sorted], dtype=float)
        if np.unique(x).size < 2:
            continue
        n_valid = len(x)
        frac = min(1.0, max(0.3, 5.0 / n_valid))

        # Compute total ion current per sample, ignoring missing values.
        arr = df[cols_sorted].to_numpy(dtype=float)
        totals = np.nansum(arr, axis=0)
        totals = np.where(totals <= 0, floor, totals)
        log_totals = np.log2(totals)

        order = np.argsort(x)
        x_sorted = x[order]
        log_totals_sorted = log_totals[order]
        try:
            trend_log_sorted = lowess(
                log_totals_sorted,
                x_sorted,
                frac=frac,
                it=0,
                is_sorted=True,
                return_sorted=False,
            )
        except Exception:
            continue
        if trend_log_sorted.shape[0] != n_valid:
            continue
        trend_log = np.empty(n_valid)
        trend_log[order] = trend_log_sorted
        mean_trend = np.nanmean(trend_log)
        # Scale each sample so its TIC matches the mean TIC trend.
        scale_log = mean_trend - trend_log
        scale_factors = 2.0 ** scale_log
        for fid in df.index:
            y = df.loc[fid, cols_sorted].to_numpy(dtype=float)
            result.loc[fid, cols_sorted] = y * scale_factors
    return result


def _ruv_iii_c(
    df: pd.DataFrame,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    control_features: Optional[List[str]] = None,
    n_unwanted_factors: int = 1,
) -> pd.DataFrame:
    """Simplified RUV-III-C batch correction using negative control features.

    For each feature, the unwanted variation is estimated from a set of negative
    controls that are non-missing on the same samples and then removed while
    preserving the biological group effect encoded in ``sample_meta``.
    """
    import numpy.linalg as la

    floor = _positive_floor(df) / 2.0
    Y = df.copy().astype(float)
    Y = Y.replace(0, np.nan).fillna(floor)
    # Work with samples as rows, features as columns.
    Yt = Y.T
    samples = list(Yt.index)
    features = list(Yt.columns)
    n_features = len(features)
    if n_features == 0 or len(samples) == 0:
        return df

    # Biological design matrix M from groups.
    groups = pd.Series({s: sample_meta.get(s, "unknown") for s in samples})
    M = pd.get_dummies(groups, dtype=float)
    if M.shape[1] == 0:
        M = pd.DataFrame({"intercept": np.ones(len(samples))}, index=samples)

    # Auto-select control features if not provided: choose features with low CV.
    if not control_features:
        mean = Yt.mean()
        std = Yt.std()
        cv = std / mean.replace(0, np.nan)
        control_features = cv.dropna().nsmallest(max(1, n_unwanted_factors)).index.tolist()
    control_features = [c for c in control_features if c in features]
    if not control_features:
        control_features = features[: max(1, n_unwanted_factors)]

    result_T = Yt.copy()
    k = max(1, n_unwanted_factors)

    for target in features:
        obs_mask = df.loc[target, samples].notna().to_numpy()
        if obs_mask.sum() < 2:
            continue
        obs_idx = np.array(samples)[obs_mask]
        Y_sub = Yt.loc[obs_idx]
        M_sub = M.loc[obs_idx].to_numpy(dtype=float)

        # Choose negative controls that are non-missing for all obs_idx and exclude target.
        available = [c for c in control_features if c != target and Y_sub[c].notna().all()]
        if not available:
            available = [c for c in control_features if c != target and Y_sub[c].notna().any()]
        if not available:
            # No controls: just regress out group effect.
            y = Y_sub[target].to_numpy(dtype=float)
            if M_sub.shape[1] > 1:
                alpha = la.pinv(M_sub) @ y
                result_T.loc[obs_idx, target] = y - M_sub @ alpha
            continue

        Y_ctl = Y_sub[available].to_numpy(dtype=float)
        # Estimate and remove biological effects from controls.
        alpha_hat = la.pinv(M_sub) @ Y_ctl
        R = Y_ctl - M_sub @ alpha_hat
        # Estimate unwanted factors from residuals.
        try:
            U, s, Vt = la.svd(R, full_matrices=False)
        except Exception:
            continue
        rank = min(k, U.shape[1] - 1, U.shape[0] - 1)
        if rank < 1:
            continue
        W = U[:, :rank]
        X = np.hstack([M_sub, W])
        y = Y_sub[target].to_numpy(dtype=float)
        try:
            coeffs = la.pinv(X) @ y
        except Exception:
            continue
        beta = coeffs[M_sub.shape[1] :]
        corrected = y - W @ beta
        result_T.loc[obs_idx, target] = corrected

    result = result_T.T
    # Restore original missing positions.
    result = result.where(df.notna())
    return result


def _apply_batch_correction(
    df: pd.DataFrame,
    method: str,
    sample_meta: Dict[str, str],
    sample_batch: Dict[str, str],
    reference_group: Optional[str] = None,
    control_features: Optional[List[str]] = None,
    n_unwanted_factors: int = 1,
) -> pd.DataFrame:
    if method == "reference_group":
        if not reference_group:
            raise HTTPException(status_code=400, detail="reference_group is required for reference_group scaling")
        return _reference_control_scale(df, sample_meta, sample_batch, reference_group)
    if method == "log2fc_control":
        if not reference_group:
            raise HTTPException(status_code=400, detail="reference_group is required for log2fc_control")
        return _log2fc_control(df, sample_meta, sample_batch, reference_group)
    if method == "mean_centering":
        return _mean_center(df, sample_batch)
    if method == "median_centering":
        return _median_center(df, sample_batch)
    if method == "quantile_normalization":
        return _quantile_normalize(df)
    if method == "combat":
        return _combat_empirical_bayes(df, sample_meta, sample_batch)
    if method == "loess_signal_drift":
        return _loess_signal_drift(df, sample_batch)
    if method == "ruv_iii_c":
        return _ruv_iii_c(df, sample_meta, sample_batch, control_features=control_features, n_unwanted_factors=n_unwanted_factors)
    raise HTTPException(status_code=400, detail=f"Unknown batch correction method: {method}")


def _from_combined_df(
    df: pd.DataFrame,
    project_id: int,
    name: str,
    feature_type: str,
    sample_meta: Dict[str, str],
    feature_meta: List[Dict[str, Any]],
    history_step: Dict[str, Any],
) -> models.Dataset:
    data_matrix = {}
    for col in df.columns:
        data_matrix[str(col)] = [_to_json_safe(v) for v in df[col].tolist()]
    return models.Dataset(
        project_id=project_id,
        source_file_id=None,
        name=name,
        feature_type=feature_type,
        data_matrix=data_matrix,
        sample_metadata={str(k): str(v) for k, v in sample_meta.items()},
        feature_metadata=[{k: _to_json_safe(v) for k, v in m.items()} for m in feature_meta],
        processing_history=[history_step],
    )


async def combine_datasets(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    dataset_ids: List[int],
    method: str,
    batch_assignment: Optional[Dict[str, str]],
    reference_group: Optional[str],
    output_name: Optional[str],
    control_features: Optional[List[str]] = None,
    n_unwanted_factors: int = 1,
) -> models.Dataset:
    if method not in VALID_BATCH_METHODS:
        raise HTTPException(status_code=400, detail=f"Invalid method. Choose from {sorted(VALID_BATCH_METHODS)}")
    if len(dataset_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two datasets are required for batch combination")

    # load datasets
    result = await db.execute(
        select(models.Dataset)
        .join(models.Project)
        .where(
            models.Dataset.id.in_(dataset_ids),
            models.Dataset.project_id == project_id,
            models.Project.owner_id == user_id,
        )
    )
    datasets = result.scalars().all()
    if len(datasets) != len(dataset_ids):
        raise HTTPException(status_code=404, detail="One or more datasets not found")

    combined, sample_meta, sample_batch, feature_meta = _build_combined_frame(
        list(datasets), batch_assignment
    )
    corrected = _apply_batch_correction(
        combined,
        method,
        sample_meta,
        sample_batch,
        reference_group=reference_group,
        control_features=control_features,
        n_unwanted_factors=n_unwanted_factors,
    )

    # choose a sensible name
    default_name = f"combined_{method}"
    if output_name:
        name = str(output_name).strip()
    else:
        name = default_name

    feature_type = datasets[0].feature_type
    history_step = {
        "step": "batch_combine",
        "method": method,
        "reference_group": reference_group,
        "control_features": control_features,
        "n_unwanted_factors": n_unwanted_factors,
        "batch_assignment": batch_assignment,
        "source_dataset_ids": dataset_ids,
        "source_dataset_names": [d.name for d in datasets],
    }

    new_dataset = _from_combined_df(
        corrected,
        project_id,
        name,
        feature_type,
        sample_meta,
        feature_meta,
        history_step,
    )
    db.add(new_dataset)
    await db.commit()
    await db.refresh(new_dataset)
    return new_dataset
