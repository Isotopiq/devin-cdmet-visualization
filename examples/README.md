# Example Import Files

Use these files to test the import pipeline end-to-end.

- `example-compound-discoverer-export.xlsx` — Thermo Compound Discoverer `Compounds` sheet export.
- `example-compound-discoverer-metadata.xlsx` — Sample metadata mapping `Sample`, `File`, `Sample Identifier`, `Sample Type`, `Condition`.
- `example-lipidsearch-export.txt` — LipidSearch 5.2.7 tab-delimited results export.
- `example-lipidsearch-alignment.txt` — Optional LipidSearch alignment table mapping `s##-#` sample IDs to group names.

## Quick test

1. Sign in with the demo credentials from `.env.template`.
2. Create a project.
3. On **Import Data**, upload the Compound Discoverer export (and metadata) or the LipidSearch export (and optional alignment).
4. Select the sheet/file, confirm detected format, assign sample groups, and import.
5. Explore the data table, statistics, plots, heatmap, PCA, volcano, isotope tracing, and reports.
