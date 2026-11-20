FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    JOBKIT_DATA=/app/data

WORKDIR /app

COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt

COPY . .
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

ENTRYPOINT ["python", "rolescan.py"]
CMD ["doctor"]
