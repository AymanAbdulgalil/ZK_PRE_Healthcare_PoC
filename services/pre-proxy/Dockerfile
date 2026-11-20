# IMAGE: pre-proxy  (FastAPI -- proxy re-encryption node; built once, run as 3 replicas: pre-proxy-1/2/3)
#
# --- builder ----------------------------------------------------------------
# Without a wheel pip builds from source; Debian's rustc is too old, so use rustup.
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain stable
ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /build
COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Parallel image builds can exceed pip's 15 s default read timeout.
RUN pip install --no-cache-dir --default-timeout=120 --retries=10 -r requirements.txt

# --- runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY app ./app

# kfrags are memory-only and compose mounts the filesystem read-only.
# User is 'preproxy' because Debian already ships a 'proxy' account.
RUN useradd --system --uid 1000 preproxy \
    && chown -R preproxy:preproxy /app
USER preproxy

EXPOSE 9001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001"]