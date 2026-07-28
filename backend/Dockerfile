FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies without building the package itself, so this layer is
# cached unless pyproject.toml changes.
COPY pyproject.toml .
RUN python - <<'PY'
import tomllib
with open('pyproject.toml', 'rb') as f:
    deps = tomllib.load(f)['project']['dependencies']
with open('requirements.txt', 'w') as f:
    f.write('\n'.join(deps) + '\n')
PY
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000
