FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libglib2.0-0 libnss3 libxss1 libfontconfig1 libfreetype6 libpng16-16 \
    libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 \
    libgbm1 libasound2 \
    fonts-liberation fonts-liberation2 fonts-dejavu fonts-dejavu-core \
    fonts-inter fonts-inter-variable \
    fonts-roboto fonts-roboto-slab \
    fonts-adobe-sourcesans3 \
    fonts-open-sans fonts-lato fonts-montserrat \
    fonts-noto-core fonts-noto-mono fonts-noto-cjk \
    fonts-freefont-ttf fonts-droid-fallback \
    fonts-firacode fonts-jetbrains-mono fonts-quicksand \
    r-base r-base-dev \
    r-cran-ggplot2 r-cran-pheatmap r-cran-jsonlite \
    r-cran-rcolorbrewer r-cran-scales r-cran-ggrepel \
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
