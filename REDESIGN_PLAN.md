# Metabolomics Platform — Commercial-Grade Redesign Plan

## Goal
Transform the current functional scaffold into a polished, commercial-quality metabolomics / lipidomics / isotope-tracing analysis platform comparable to MetaboAnalyst and LipidOne.eu in depth, clarity, and visual finish, while remaining responsive and deployable.

## Phase 1 — Foundation & Reliability
1. **Production hardening**
   - Migrate all Plotly/NumPy/SciPy results through a strict JSON-safe sanitizer (no `NaN`, `inf`, `None` leakage).
   - Add comprehensive backend tests covering each importer, preprocessing step, statistical test, and plot type with real example data.
   - Add frontend integration tests for the import → dataset → stats → plot workflow.
   - Add backend request validation and graceful user-facing errors for malformed uploads.

2. **Data model expansion**
   - Separate `Project`, `Experiment`, `Run`, and `Dataset` concepts so users can group replicates / batches / ionization modes.
   - Store raw intensity matrix, normalized matrix, and audit log of every transformation (reversible pipeline).
   - Add support for tracer metadata (isotope, max label, natural abundance correction settings) at the experiment level.

3. **Import wizard overhaul**
   - Stepper UI: Upload → Format detection → Sheet / alignment selection → Column mapping → Group assignment → Metadata mapping → Validation → Summary.
   - Live preview table with first 10 rows and column-type badges.
   - Manual column override when detection is uncertain.
   - Support for multi-file imports (positive + negative ionization, alignment table, identification table).

## Phase 2 — Analysis Modules
1. **Preprocessing pipeline**
   - Presets: none, MetaboAnalyst-style, LipidSearch-ready, isotope-tracing.
   - Per-step controls with explanatory tooltips: missing-value filtering, blank subtraction, QC CV filtering, duplicate aggregation, imputation (LOD, KNN, RF), log transformation, scaling, normalization (total area, internal standard, protein, DNA, cell number, tissue weight, custom), batch correction.
   - Visual pipeline graph showing current state and allowing step reorder / toggle.

2. **Statistics**
   - Full suite already scaffolded; add effect sizes, confidence intervals, post-hoc tests, and ANOVA with interaction terms.
   - Add pairwise comparison builder (multiple contrasts) and save results as an `Analysis` object.
   - Export full result tables (CSV, Excel) with embedded formulas/notes.

3. **Visualization polish**
   - **Volcano:** selectable label column, draggable significance thresholds, density-aware label placement, side panels for up/down gene-set summaries, download PNG/SVG/PDF/CSV.
   - **PCA:** scree plot with Kaiser/Nyström threshold, loadings plot with search/filter, 3D score plot toggle, ellipses by group, biplot arrows with label collision avoidance.
   - **Heatmap:** abundance (default) and correlation modes, top-N variable feature selection (most variable, ANOVA F, fold change), row/column dendrograms, group color bars, z-score per row, custom color scales, download.
   - **Box/violin/dot/paired plots:** group ordering, jitter, statistical annotation brackets with test labels, outlier styling.
   - **RT vs m/z:** grade-based shapes, lipid-class color overlay, zoom and lasso selection.

4. **Isotope tracing**
   - Table of isotopologue fractions per sample/feature.
   - Stacked bar charts, enrichment time courses, tissue/condition comparison, mean labeled atoms, precursor-normalized enrichment, pooled labeling.
   - Natural-abundance correction UI and tracer purity input.

5. **Lipidomics-specific views**
   - Class-level abundance / composition bar and pie charts.
   - Carbon-number and double-bond plots.
   - Fatty-acyl composition treemap / sunburst.

6. **Pathway & flux**
   - Replace placeholder pathway builder with a real Cytoscape.js or D3 force graph.
   - KEGG/HMDB/ChEBI search and mapping.
   - Node color by abundance/FC/significance/isotope enrichment, size by magnitude, edge thickness by reaction confidence.
   - Clear legend distinguishing measured vs inferred vs modeled flux.
   - SBML and user node-edge file import.

## Phase 3 — User Experience & Design
1. **Design system**
   - Adopt a cohesive color system (Tailwind slate/indigo/emerald/amber/rose) with dark mode.
   - Consistent spacing, typography, loading states, skeletons, empty states, and error toasts.
   - Replace generic Plotly defaults with a custom theme (fonts, color palette, grid styling, annotations).

2. **Navigation & dashboard**
   - Persistent left sidebar with collapsible sections (Project, Import, Process, Explore, Analyze, Visualize, Reports).
   - Project dashboard: cards for datasets, recent analyses, QC summary, sample/group counts.
   - Breadcrumbs and page-level actions.

3. **Tables**
   - Replace basic HTML tables with a virtualized data grid (TanStack Table) with sorting, filtering, pagination, column visibility, and export.
   - Compound / lipid detail side panel with all metadata, plots, and analyses.

4. **Workflow guidance**
   - Contextual help, tooltips, and a "next recommended step" indicator.
   - Progress indicators for long-running imports / analyses.

## Phase 4 — Collaboration, Export & Administration
1. **Reports**
   - One-click PDF/HTML report generator combining dataset summary, QC, stats, and selected plots.
   - Configurable sections and branding (logo, colors).

2. **User management**
   - Complete admin panel already started: user CRUD, role-based access, logs, settings, logo upload, retention policies.

3. **API & extensibility**
   - OpenAPI documentation, programmatic API token generation, webhook / job-queue support for long analyses.

## Suggested Order of Attack
1. Harden JSON serialization and expand backend tests (prevents real-data crashes).
2. Refactor Plotly wrappers into a shared, theme-aware `Plot` system with PNG/SVG/PDF export.
3. Rebuild Volcano, PCA, and Heatmap with the above design specs.
4. Replace HTML tables with TanStack Table and add compound/lipid detail panels.
5. Add preprocessing pipeline UI and experiment/run data model.
6. Build lipidomics and isotope-tracing specialized views.
7. Implement real pathway graph and report generator.

## Estimated Scope
This is several days of focused work. The current codebase is a solid scaffold; each phase builds on the existing FastAPI + React + PostgreSQL + Docker foundation.
