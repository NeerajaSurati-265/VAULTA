# One image for both the VAULTA API (FastAPI) and the UI (Streamlit);
# docker-compose.yml picks the command. Ollama runs in its own container.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # VAULTA promises zero external calls; Streamlit would otherwise send usage stats
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes,
# not on every code change. No apt packages: the PyMuPDF and faiss-cpu wheels
# bundle their native libraries.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 1000 vaulta

# Code plus the sample documents/datasets (fictional demo data, see
# scripts/make_sample_docs.py). The index is never baked in: it is built at
# startup into data/index, which compose mounts as a named volume. The
# directory is created here, owned by vaulta, so a fresh volume inherits that.
COPY app/ app/
COPY data/documents/ data/documents/
COPY data/spreadsheets/ data/spreadsheets/
RUN mkdir -p data/index && chown vaulta:vaulta data/index

USER vaulta

EXPOSE 8000 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
