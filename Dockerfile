FROM python:3.12-slim

WORKDIR /app

# System deps (build-only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev gosu && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Create data/logs dirs
RUN mkdir -p data logs

# Install the package + postgres driver
RUN pip install --no-cache-dir ".[postgres]"

# Run as non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home appuser && \
    chown -R appuser:appuser /app

# Entrypoint: fix ownership of mounted volumes, then drop to appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8501

ENTRYPOINT ["/entrypoint.sh"]
# Default: run the Streamlit dashboard
CMD ["sh", "-c", "alembic upgrade head && streamlit run src/valuesentinel/dashboard/app.py --server.port=8501 --server.address=0.0.0.0"]
