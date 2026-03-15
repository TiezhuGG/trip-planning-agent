ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=

WORKDIR /app

COPY requirements.txt .
RUN set -eux; \
    if [ -n "$PIP_TRUSTED_HOST" ]; then \
      pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" uv; \
      pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" -r requirements.txt; \
    else \
      pip install --no-cache-dir --index-url "$PIP_INDEX_URL" uv; \
      pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt; \
    fi

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
