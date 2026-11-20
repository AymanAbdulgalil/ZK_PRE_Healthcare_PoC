# IMAGE: owner  (Streamlit GUI -- data owner/custodian client)
#
# --- builder: umbral-pre may need a Rust toolchain + C linker to build ----
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

# --- runtime: no compiler, just the built venv + app code -----------------
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY app ./app

# Streamlit telemetry spams PermissionErrors for this non-root user.
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Owned by the app user so the `owner-identity` volume inherits it, not root.
RUN mkdir -p /app/identity \
    && useradd --system --uid 1000 owner \
    && chown -R owner:owner /app
USER owner

# No telemetry; a writable HOME for libraries that assume one.
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV HOME=/app

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/main.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]