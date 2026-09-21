# Developer Handoff — Metabolomics Visualization Platform

This doc is written for the next developer taking over the project. It covers the stack, the current feature set, the most recent changes, and the bugs/issues that still need attention.

## 1. Stack & Architecture

- **Frontend:** React + TypeScript + Vite, Tailwind CSS, Plotly.js via `react-plotly.js`, `axios` API layer.
  - Entry: `frontend/src/main.tsx`
  - Main pages: `frontend/src/pages/Visualize.tsx`, `QC.tsx`, `Preprocessing.tsx`, `Home.tsx`
  - Shared state: `frontend/src/context/` (PlotConfigContext, ProjectContext)
  - API wrappers: `frontend/src/api.ts`
- **Backend:** FastAPI, SQLAlchemy, Pandas, NumPy, Plotly, Kaleido, Matplotlib fallback, scikit-learn/scipy.
  - Main: `backend/app/main.py`
  - Routers: `backend/app/routers/analysis.py`
  - Core services:
    - `backend/app/services/plots.py` — Plotly plot generation for Visualize tab
    - `backend/app/services/qc.py` — QC analysis and Plotly QC figures
    - `backend/app/services/pdf_report.py` — PDF report builder (covers, summary tables, image embedding)
    - `backend/app/services/_pdf_plot_fallback.py` — Matplotlib fallback when Kaleido fails
    - `backend/app/services/plots_r/` — R/ggplot2 static plot engine (optional, selected per-plot)
    - `backend/app/services/detection.py` — file format detection and Compound Discoverer metadata parsing
- **Database:** PostgreSQL
- **Deployment:** Docker Compose via `docker-compose.easypanel.yml` (Easypanel host ports mapped to container ports)
  - backend host `18457` → container `8000`
  - frontend host `13457` → container `80`
  - db host `15437` → container `5432`

## 2. Current Feature Set

### Visualize tab
- Plot renderer can be toggled per plot:
  - **Plotly** (interactive, default)
  - **R static** (`plots_r/*.R` templates rendered server-side to PNG)
- Plot styles (Plotly only):
  - `default`
  - `publication`
  - `lipidone` (teal/orange palette, LipidOne-like bar/volcano styling)
- Plot types: PCA (score/loading/biplot/scree), volcano, per-lipid bars, lipid class bars, heatmap (abundance/correlation), chain space, functional indices, food-profile indices, outlier, PLS-DA/OPLS-DA, PERMANOVA, biomarker panel.
- Global group filter in `Visualize.tsx` lets users include/exclude groups.
  - For comparison plots (volcano, per-lipid bars, etc.) the per-plot Group A / Group B dropdowns still take precedence; excluded groups are respected for overview plots.
  - Blank/QC/solvent/standard/pool/NTC groups are unchecked by default.
- Lipid class tab has a class selector (checkbox grid) wired to both Plotly and R renderers.

### QC tab
- Runs dataset-level QC via `GET /analysis/{project_id}/dataset/{dataset_id}/qc`
- Plots: TIC, missing %, detected features, log2 intensity distribution, per-group CV, QC pool drift, QC pool correction, PCA, correlation heatmap.
- QC PDF export (`POST .../qc/pdf`) with cover page + summary tables + embedded plot pages.
- Users can now choose which QC plots to include via checkboxes in `frontend/src/pages/QC.tsx`.

### Preprocessing / export
- MetaboAnalyst- and LipidOne-compatible CSV exports.
- Optional **Clean sample names** checkbox removes `Area:`, `.RAW`/`_raw`, and `(FXX)` from sample/column names.

### Compound Discoverer support
- Data file headers: `Name`, `Formula`, `m/z`, `RT`, `Area:` columns become sample intensity columns.
- Metadata files are detected by `Sample Identifier`/`File` columns.
- Group assignment uses `Condition` first, then `Sample Type` for blanks/QCs/pools/standards.
- See `backend/app/services/detection.py` for the matching regex and fallback logic.

## 3. Latest Changes (this commit)

### QC PDF
- `backend/app/services/pdf_report.py`
  - Empty `selected_plots` now falls back to all available plots (previously an empty list produced a 2-page cover+summary PDF with no charts).
- `frontend/src/pages/QC.tsx`
  - Preview / Export buttons are disabled when no plots are selected, preventing accidental empty reports.

### QC x-axis autosizing (hardened)
- `backend/app/services/qc.py`
  - `_format_qc_xaxis()` now dynamically sizes the tick font so **every sample gets a label** for all QC bar/box plots.
  - Only thins labels as an absolute last resort (when the count is so high that even a minimum font cannot fit).
  - Forces `tickmode="array"`, `categoryorder="array"`, and `ticklabeloverflow="allow"` so Plotly does not drop bars or labels.
- `backend/app/services/plots.py`
  - `_apply_base_layout()` now detects an existing `tickmode="array"` x-axis and refuses to overwrite `tickfont`, `tickangle`, or the bottom margin. This prevents unrelated layout changes from clobbering the QC label fix.
- `backend/tests/test_qc.py`
  - New regression tests assert `tickmode="array"` and one label per sample for `tic`, `missing_pct`, `detected_features`, `log2_intensity`, and one label per group for `cv_by_group`.
  - Test also asserts `_apply_base_layout()` preserves an already-configured array x-axis.

### PCA NaN handling
- `backend/app/services/plots.py`
  - Old code: `X = df.dropna().T` dropped any feature (row) with even one missing value, often leaving too few features for PCA.
  - New code: drops only all-NaN rows/columns, transposes, then imputes remaining missing values before `StandardScaler` + `PCA_SKL`.
  - `components` is clamped to the cleaned matrix shape and the PCA block is wrapped in `try/except`.

### Correlation heatmap clustering
- `backend/app/services/plots.py`
  - Old code: `pdist(df.T.values)` on raw data with missing values raised `ValueError: The condensed distance matrix must contain only finite values`.
  - New code: strips all-NaN samples/features, replaces remaining `NaN`/`Inf` with `0` for clustering only, and reorders the cleaned `sub` DataFrame.
  - Top x-axis labels now use `tickmode="array"` with auto-rotation and tick skipping.

### Frontend QC plot selection
- `frontend/src/pages/QC.tsx`
  - `selectedPlots` checkbox panel already existed; disabled state on the PDF buttons now guards the empty case.

## 4. Known Issues / Potential Unresolved Bugs

### QC PDF corruption in live deployment
- **Symptom:** User's live QC PDFs still show `zlib error: incorrect header check` and 2-page cover+summary output even after backend fixes.
- **Most likely cause:** The deployed Docker container is running pre-fix code. A local synthetic test (`backend/app/services/pdf_report.py::build_qc_pdf`) produced a valid 7-page PDF with embedded plots.
- **Action needed:** Rebuild + redeploy backend container; see Section 6.

### QC plots still look crowded on very long sample names
- `_format_qc_xaxis()` improves things but the heuristic is based on fixed `plot_width_px=1000` pixels.
- If sample names are >20 characters and >40 samples, labels rotate to `-90°` and are heavily down-sampled. May still look dense if the chosen PDF image width is large (`2400px`).
- Future improvement: pass actual figure width through the PDF pipeline, or let the frontend request a width.

### Correlation heatmap with >60 samples
- Tick skipping is enabled, but the heatmap cells become very small. The colorbar and dendrogram are not rendered in the Plotly QC version because `qc.py` calls `generate_plot(... plot_type="heatmap" ...)` with default parameters and no dendrogram overlay.
- If users report missing dendrogram in QC correlation heatmap, the `correlation_heatmap` branch in `plots.py` only clusters columns; row/column dendrograms are not drawn.

### PCA with many missing values
- The new imputation (`X.fillna(X.min().min() / 2)`) is a simple constant fill. If the dataset is >50% missing, PCA results may be dominated by the imputed floor.
- Consider a more appropriate imputation (k-NN, mean-per-group) if users complain.

### `kaleido` deprecation warnings
- Tests pass but emit warnings about `plotly.io.kaleido.scope.*` being deprecated. These come from the `kaleido` package and do not break functionality today, but the package will need updating after Sep 2025.

### Frontend build chunk size warning
- `npm run build` warns that the JS chunk is >5 MB. It is a pre-existing Vite warning and does not block builds. Code-splitting would help but is out of scope.

### R static engine
- R plots are an **optional add-on**, not a replacement for Plotly. The `engine` parameter (`"plotly"`/`"r"`) and `plot_style` (`default`/`publication`/`lipidone`) are separate. Ensure any future plot type supports both or at least gracefully falls back to Plotly.
- The R environment is installed in `backend/Dockerfile`. Adding new fonts requires rebuilding the backend image.

## 5. Running & Testing Locally

```bash
cd /home/ubuntu/repos/metabolomics-platform/backend
python -m pytest -q
# expected: 84 passed, 1 skipped

cd /home/ubuntu/repos/metabolomics-platform/frontend
npm run lint
npm run build
```

To manually generate a QC PDF from a synthetic dataset for inspection:

```python
# run from backend/ directory
from app.models import Dataset
from app.services.pdf_report import build_qc_pdf
# ... build a Dataset with data_matrix dict, sample_metadata, feature_metadata ...
pdf_bytes = build_qc_pdf(dataset, project_name='Test', selected_groups=None, selected_plots=None)
open('/tmp/qc_test.pdf','wb').write(pdf_bytes)
```

## 6. Redeploy Instructions

```bash
cd /path/to/devin-cdmet-visualization
git pull
docker compose -f docker-compose.easypanel.yml up -d --build
```

If you only need the backend rebuilt:

```bash
docker compose -f docker-compose.easypanel.yml up -d --build metabolomics-backend-easypanel
```

Always redeploy after any backend change because the live container is almost certainly stale when PDF corruption is reported.

## 7. Useful File References

- QC plot generation: `backend/app/services/qc.py` (`qc_analysis`, `_bar_figure`, `_log2_box_figure`, `_cv_box_figure`, `_format_qc_xaxis`)
- General Plotly plots: `backend/app/services/plots.py` (`generate_plot`, PCA block ~line 2380, correlation heatmap block ~line 2144)
- PDF builder: `backend/app/services/pdf_report.py` (`build_qc_pdf`, `_fig_to_png`, `_fit_image`, `_draw_table`)
- Matplotlib fallback: `backend/app/services/_pdf_plot_fallback.py`
- R templates: `backend/app/services/plots_r/`
- Frontend QC page: `frontend/src/pages/QC.tsx`
- Frontend group/style state: `frontend/src/context/PlotConfigContext.tsx`, `frontend/src/components/PlotStyling.tsx`
- Compound Discoverer detection: `backend/app/services/detection.py`
