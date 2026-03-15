ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} ${PIP_TRUSTED_HOST:+--trusted-host ${PIP_TRUSTED_HOST}} uv \
    && pip install --no-cache-dir --index-url ${PIP_INDEX_URL} ${PIP_TRUSTED_HOST:+--trusted-host ${PIP_TRUSTED_HOST}} -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
