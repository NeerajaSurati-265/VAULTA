# VAULTA — Sovereign Industrial AI Workbench

> **Confidential industrial intelligence — processed entirely on-premise.**

VAULTA is a sovereign, on-premise Agentic AI workbench designed for confidential industrial environments where sensitive documents, operational data, SOPs, and engineering analysis must remain within the organization's infrastructure.

It combines open-weight local LLMs, specialized agents, local RAG, deterministic data analysis, verification, and automated engineering deliverables into a single industrial investigation workflow.

---

## 🎯 Problem

Industrial organizations often work with highly sensitive information:

- Maintenance and inspection reports
- Standard Operating Procedures (SOPs)
- Equipment telemetry and operational data
- Engineering correspondence
- Failure and downtime records
- Internal technical knowledge

Sending this information to cloud-based AI services can create unacceptable confidentiality, compliance, and data-sovereignty risks.

VAULTA addresses this by providing an **AI workflow that runs locally**, using an open-weight model through a local inference server.

---

## 🚀 What VAULTA Does

An engineer can provide a problem such as:

> **"Investigate recurring vibration in Pump-402 and prepare an approval note."**

VAULTA then performs an end-to-end investigation:

```text
Engineering Request
        │
        ▼
    Task Router
        │
        ├───────────────┬────────────────┐
        ▼               ▼                ▼
 Document Agent     Data Agent      Knowledge Agent
        │               │                │
        ▼               ▼                ▼
   PDF Analysis    Pandas Analysis   Local RAG / FAISS
        │               │                │
        └───────────────┴────────────────┘
                        │
                        ▼
               Root-Cause Synthesis
                  Local Qwen LLM
                        │
                        ▼
                  Verification
                        │
                        ▼
                Approval Note (.DOCX)
```

---

## 🖥️ System Requirements

- **OS:** Ubuntu 22.04+ recommended (Windows works through WSL2)
- **Python:** 3.10+
- **RAM:** 8 GB minimum, 16 GB recommended
- **Storage:** 10 GB+ free space
- **CPU:** Modern x86_64 processor
- **GPU:** Not required for the default Qwen 2.5 3B model
- **Git** and **curl**
- **Ollama:** Required (local LLM server)

---

## 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/NeerajaSurati-265/VAULTA.git
cd VAULTA
```

### 2. Create a Python virtual environment

```bash
sudo apt install -y python3-venv   # only if `python3 -m venv` fails
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install Ollama and pull the model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
ollama list          # qwen2.5:3b should be listed
```

On Ubuntu the installer runs Ollama as a background service. If `ollama list` says it cannot connect, start the server in a separate terminal:

```bash
ollama serve
```

No OpenAI/Gemini API key is needed. All inference runs locally through Ollama.

### 5. Run VAULTA

```bash
./run.sh
```

`run.sh` checks that Ollama is reachable and the model is pulled, starts the FastAPI backend on port 8000, waits for it to be healthy, and then starts the Streamlit UI. Open the URL Streamlit prints (usually http://localhost:8501). Press `Ctrl+C` to stop both.

---

## ⚡ Quick Setup

For a fresh Ubuntu machine:

```bash
git clone https://github.com/NeerajaSurati-265/VAULTA.git
cd VAULTA

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b

./run.sh
```

---

## 🔧 Running Manually (two terminals)

The UI talks to the backend over HTTP, so **both** must be running. From the repo root, with the virtual environment active in each terminal:

**Terminal 1: backend (FastAPI)**

```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2: UI (Streamlit)**

```bash
source .venv/bin/activate
PYTHONPATH=. streamlit run app/ui.py
```

Check the backend with `curl http://127.0.0.1:8000/health`.

---

## ⚙️ Configuration (environment variables)

All settings live in `app/config.py` and can be overridden with environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server URL |
| `VAULTA_MODEL` | `qwen2.5:3b` | Ollama model used for all LLM calls |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for one Ollama response |
| `VAULTA_BACKEND_URL` | `http://127.0.0.1:8000` | Backend URL used by the UI (and by `run.sh` to pick host/port) |
| `VAULTA_LOG_LEVEL` | `INFO` | Backend log level (`DEBUG`, `INFO`, `WARNING`, ...) |

Data paths are resolved relative to the repo root, so it does not matter which directory you start from:

- `data/documents/` – PDFs auto-indexed into the knowledge base at startup
- `data/spreadsheets/` – demo datasets
- `data/index/` – saved knowledge-base index (generated; not committed)

Example:

```bash
VAULTA_MODEL=qwen2.5:7b OLLAMA_TIMEOUT=600 ./run.sh
```
