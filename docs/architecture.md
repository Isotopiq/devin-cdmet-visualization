# Architecture

## Backend

- `app/main.py` — FastAPI application factory and router registration.
- `app/models.py` — SQLAlchemy declarative models (User, Project, UploadedFile, Dataset, Analysis).
- `app/schemas.py` — Pydantic request/response models.
- `app/auth.py` — bcrypt password hashing and JWT authentication.
- `app/routers/` — REST API endpoints.
- `app/services/` — Business logic: format detection, import, preprocessing, statistics, plotting, isotope tracing, pathway mapping.
- `alembic/` — Database migrations.

## Frontend

- `src/App.tsx` — Top-level routing and login gate.
- `src/components/Layout.tsx` — Left navigation sidebar.
- `src/pages/` — Projects, Import, Data Table, Statistics, Compound Plots, Heat Map, PCA, Volcano Plot, Isotope Tracing, Pathway Mapping, Reports, Settings.
- `src/api.ts` — Axios HTTP client with JWT interceptor.

## Data Flow

1. User uploads Excel/CSV/TSV into a project.
2. Backend detects vendor format and lists sheets/columns.
3. Frontend previews columns and allows mapping/group assignment.
4. Backend imports selected sheet into a Dataset (data matrix + feature/sample metadata).
5. Preprocessing creates a new Dataset with a recorded, reversible history.
6. Statistics and plots operate on a Dataset and save results as Analysis records.
7. Isotope tracing and pathway modules consume Datasets and return Plotly JSON figures.
