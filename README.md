# MetaboScope — Metabolomics, Lipidomics & Stable-Isotope Tracing Platform

A production-ready, Dockerized web application for importing, analyzing, and visualizing metabolomics, lipidomics, and stable-isotope tracing data exported from Thermo Compound Discoverer and LipidSearch 5.

## Technology Stack

- **Frontend:** React 18, TypeScript, Tailwind CSS, Flowbite, Plotly
- **Backend:** Python 3.10+, FastAPI, SQLAlchemy 2 (async), Alembic, Pandas, NumPy, SciPy, Statsmodels, Scikit-learn
- **Database:** PostgreSQL 15
- **Packaging:** Docker Compose

## Quick Start

1. Copy the environment template and edit secrets:
   ```bash
   cp .env.template .env
   ```

2. Build and start all services:
   ```bash
   docker compose up --build
   ```

3. Open the frontend at http://localhost:13000 and the backend docs at http://localhost:18000/docs.

## Development

### Backend

```bash
cd backend
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

Run tests:
```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Features

- JWT-based user authentication and private projects
- Direct upload of Excel, CSV, and TSV files
- Automatic format detection for Compound Discoverer and LipidSearch 5
- Manual column mapping and sample group assignment
- Preprocessing: missing-value filtering, blank subtraction, QC CV filtering, imputation, log transformation, scaling, normalization, batch correction
- Statistics: t-tests, Welch, paired, Mann-Whitney, Wilcoxon, ANOVA, Kruskal-Wallis, multiple-testing correction, effect sizes
- Interactive Plotly visualizations: bar, box, violin, dot, paired, heatmap, PCA, volcano, correlation, RT vs m/z, lipid class plots
- Stable-isotope tracing with M+0..M+n isotopologue fractions, total labeled fraction, fractional enrichment, mean labeled atoms, pooled labeling
- Pathway mapping with KEGG/HMDB/ChEBI/Reactome/SBML/custom node-edge support and visual distinction of data types

## Project Structure

```
metabolomics-platform/
├── docker-compose.yml
├── .env.template
├── backend/              FastAPI application
├── frontend/             React application
├── templates/            Example import files
├── examples/             Additional usage examples
└── docs/                 Architecture and API documentation
```

## License

MIT
