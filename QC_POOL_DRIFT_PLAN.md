# QC-Pool Drift Correction — Mega Plan

## 1. Problem statement
Long LC-MS runs often lose signal over time (source contamination, column degradation, spray instability). When a **QC-Pool** sample starts to show lower total (or per-feature) intensity, all biological samples run *after* that point are biased downward. We want an **independent drift-correction step** that uses the QC-Pool samples as a moving reference and corrects every sample based on the QC-Pool trend observed up to (and including) its run position.

## 2. Recommended approach: QC-Pool signal-drift correction
The cleanest way to implement this inside the existing pipeline is a **new preprocessing step** that runs on a single dataset, *before* total-area normalization and log transform.

Why before normalization / log?
- Ion-source drift is a **multiplicative** effect on raw intensities.
- Correcting first gives biologically meaningful normalization afterwards.
- Correcting in log space (`log I - predicted drift`) is mathematically equivalent to multiplying raw values by a scale factor.

### 2.1 Default algorithm: global TIC LOWESS
1. Identify QC-Pool samples from the selected group name(s).
2. For each QC-Pool sample compute `log2(TIC)` after a small positive floor.
3. Fit a robust LOWESS / smoothing spline of `log2(TIC)` versus run order.
4. Pick a reference level, e.g. the **median predicted log-TIC across all QC-Pool positions**.
5. For every sample (biological or QC) at its run position, compute:
   ```
   corrected_intensity = raw_intensity * 2^(ref_log - predicted_log(position))
   ```
   This scales later samples up when the QC-Pool trend declines.
6. Edge cases:
   - Samples before the first QC-Pool use the first QC-Pool prediction.
   - Samples after the last QC-Pool are extrapolated with the last local slope or kept at the last QC-Pool prediction (configurable).
   - If < 3 QC-Pool samples exist, fall back to a simple linear regression or median scaling.

### 2.2 Optional advanced mode: per-feature LOWESS
Instead of global TIC, fit a separate LOWESS curve for each feature using that feature’s QC-Pool values. This catches feature-specific ion-suppression but is noisier and should only be used when enough QC replicates exist (default off).

### 2.3 Alternative methods to expose
- `loess_tic` (default, robust)
- `linear_tic` (simple regression, good for monotonic drift)
- `spline_tic` (UnivariateSpline, smooth but needs enough QC points)
- `loess_per_feature` / `linear_per_feature` (advanced)

## 3. Pipeline placement
Add after step 7 (`_make_non_negative`) and before step 8 (`normalization`) in `preprocess_dataset`.

```
1. missing value filter
2. blank subtraction
3. QC CV filter
4. isobaric substitution
5. duplicate handling
6. imputation
7. make non-negative
7.5. QC-Pool drift correction  <-- NEW
8. normalization
9. log transform
10. batch correction
11. scaling
12. rename samples
```

## 4. New preprocessing parameters

```python
qc_pool_drift_correction: bool = False
qc_pool_group: Optional[str] = None          # sample_metadata group to treat as QC-Pool
qc_pool_method: str = "loess_tic"           # loess_tic, linear_tic, spline_tic, loess_per_feature, linear_per_feature
qc_pool_span: float = 0.75                  # LOWESS fraction (0.3-1.0)
qc_pool_target: str = "median"              # reference: median, mean, first_qc
qc_pool_extrapolate: str = "last"           # last, linear, none
```

Run order:
- **Phase 1:** use the column order in `data_matrix` as the run order.
- **Phase 2 (future):** allow an optional uploaded run-order file or `run_order` mapping per sample.

## 5. Backend changes

### 5.1 Core correction module
Create `backend/app/services/drift.py` with:
- `_qc_pool_columns(sample_metadata, qc_pool_group)` — find matching samples.
- `_run_order(df)` — return sample -> integer position (column order).
- `_fit_tic_drift(df, qc_cols, order, method, span)` — fit and return predicted log-TIC for every sample.
- `correct_qc_pool_drift(df, sample_metadata, params)` — apply correction and return corrected df + diagnostics.
- Optional `_fit_per_feature_drift` for advanced mode.

### 5.2 Preprocessing integration
In `backend/app/services/preprocessing.py`:
- Add parameters to `PreprocessingParams` / `schemas.py`.
- Add step 7.5 after `_make_non_negative` and before normalization.
- Record the QC-Pool trend and scale factors in the `history_step` dict for traceability.

### 5.3 Schemas
Update `backend/app/schemas.py` `PreprocessingParams` with the new fields.

### 5.4 QC page diagnostics
Add a QC-Pool drift plot to `backend/app/services/qc.py`:
- Raw vs. corrected total ion current (TIC) per sample, colored by group.
- QC-Pool samples highlighted.
- A second small plot showing the fitted trend and scale factors.

## 6. Frontend changes

### 6.1 Preprocessing page
In `frontend/src/pages/Preprocessing.tsx` add a "QC-Pool drift correction" card:
- Checkbox to enable.
- Dropdown to choose QC-Pool group (populate from `sample_metadata` groups; auto-select any group containing `qc` and `pool`).
- Method dropdown (`loess_tic`, `linear_tic`, `spline_tic`, `loess_per_feature`, `linear_per_feature`).
- Span slider / number input (0.3-1.0, default 0.75).
- Reference target dropdown (`median`, `mean`, `first QC`).
- Extrapolation dropdown (`last QC`, `linear`, `none`).
- Short help text: e.g. "Corrects signal drift using QC-Pool samples as a reference. Recommended before normalization."

### 6.2 QC page
Optionally show the new QC-Pool drift diagnostic plot if QC-Pool samples are present.

## 7. Validation & warnings
- If enabled but no QC-Pool group is selected or the group has < 2 samples, raise `HTTPException(400, ...)` or disable automatically.
- If QC-Pool CV is very high (> 30%) or the trend is non-monotonic, log a warning but still apply.
- When `normalization == "total_area"`, display a UI note that QC drift correction is best applied first (it already is, by pipeline order).

## 8. Testing plan
1. Unit tests in `backend/tests/test_preprocessing.py`:
   - Synthetic dataset with a known declining QC-Pool TIC; verify later biological samples are scaled up.
   - Test with < 3 QC-Pool samples falls back gracefully.
   - Test per-feature mode on synthetic data.
2. Frontend: `npm run build` and `npm run lint`.
3. End-to-end: upload a dataset with QC-Pool group, run preprocessing with QC drift correction, and verify corrected intensities in exported CSV and plots.

## 9. Open questions for you
1. Do you want **global TIC correction first**, or is **per-feature correction** the priority?
2. Should QC-Pool group be **auto-detected** from names containing `qc` + `pool`, or do you always want a manual dropdown?
3. Is **column order** in the uploaded data reliable as run order, or do you already store run order somewhere (e.g., sample metadata or filename)?
4. Should the correction be **multiplicative on raw intensities** (recommended) or additive on log intensities?

## 10. Suggested first slice
Implement `loess_tic` global correction only:
- Add parameters to `PreprocessingParams`.
- Add `backend/app/services/drift.py`.
- Wire into `preprocessing.py` before normalization.
- Add UI controls on the Preprocessing page.
- Add one unit test and a QC diagnostics plot.

Once the global version is validated, per-feature and spline variants are small extensions.
