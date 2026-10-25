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

### 4. Install Ollama and pull the models

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b          # chat / reasoning model
ollama pull nomic-embed-text    # embedding model for knowledge-base search
ollama list                     # both should be listed
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

`run.sh` checks that Ollama is reachable and the required models are pulled, starts the FastAPI backend on port 8000, waits for it to be healthy, and then starts the Streamlit UI. Open the URL Streamlit prints (usually http://localhost:8501). Press `Ctrl+C` to stop both.

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
ollama pull nomic-embed-text

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

## 🔎 How retrieval works

The knowledge base splits every PDF page into ~500-character chunks (100-character overlap) and keeps page numbers so answers can cite their source. In the default `hybrid` mode, a question is answered like this:

```text
                    question
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   BM25 keyword search       Semantic search (FAISS)
   (exact IDs, numbers:      nomic-embed-text vectors via
    "P-402", "4.5 mm/s")     local Ollama (synonyms, paraphrases)
          │ top 20                  │ top 20
          └────────────┬────────────┘
                       ▼
          Reciprocal Rank Fusion
          score = Σ 1 / (60 + rank)
                       │ top k
                       ▼
          Grounded answer from qwen2.5:3b
          (cites document + page)
```

- **BM25** is strong when the question uses the document's exact words, IDs or numbers.
- **Semantic** search finds passages that mean the same thing in different words ("shaking" ↔ "vibration").
- **RRF** combines the two lists by rank only, so the different score scales never need to be normalised. Every retrieved chunk reports its final score plus its BM25 rank and vector rank, and these appear in the UI and the execution trace.

Other modes (`VAULTA_RETRIEVAL_MODE`): `bm25` (keyword only, no embedding model), `semantic` (vectors only), `hashing` (the original hashed-keyword vectors). The saved index records its mode and embedding model; after a switch, the saved chunks are re-embedded automatically on the next start.

---

## 📏 Evaluation

`eval/questions.jsonl` holds 40 questions over the 7 PDFs in `data/documents/`, each labelled with the document and page that answers it:
- 15 **lexical**: the question uses the document's own wording
- 15 **paraphrase**: synonyms only, e.g. "shaking" for vibration, "cut off every power source" for isolate
- 10 **exact**: IDs and numbers such as `V-211`, `ISO VG 46`, `7.1 mm/s`

`hit@k` means the expected document+page appears in the top k chunks. `MRR` is the mean reciprocal rank of the first correct chunk.

| Mode | Overall hit@1 | Overall hit@3 | Overall hit@5 | Overall MRR | Lexical hit@3 | Paraphrase hit@3 | Exact hit@3 | ms/query | Indexing (s) |
|------|---|---|---|---|---|---|---|---|---|
| hashing | 35% | 55% | 72% | 0.473 | 87% | 20% | 60% | 0.2 | 0.01 |
| bm25 | 72% | 88% | 90% | 0.794 | 100% | 67% | 100% | 0.1 | 0.01 |
| semantic | 68% | 90% | 90% | 0.767 | 100% | 93% | 70% | 30.1 | 2.21 |
| **hybrid** (default) | 68% | 90% | 95% | 0.792 | 100% | 80% | 90% | 31.4 | 2.42 |

Reproduce (needs Ollama with `nomic-embed-text` for the semantic and hybrid modes):

```bash
python eval/run_eval.py --mode hybrid   # one mode
python eval/run_eval.py --mode all      # all four modes, comparison table
```

Results (including per-question ranks) are written to `eval/results/<mode>.json`.

Numbers are after U7 (SOP-PUMP-402 p.2 regenerated with its full text); hybrid ranks were unchanged question by question. The app retrieves `VAULTA_RETRIEVAL_TOP_K` = 5 chunks, so hit@5 is the figure that matters for answers.

**Caveats:** the six synthetic documents (`scripts/make_sample_docs.py`) and the questions were written by the same author, so this is a sanity benchmark for comparing modes, not an independent one. With 40 questions, one question equals 2.5 percentage points.

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests mock the LLM and embedding calls, so they run without Ollama.

---

## ⚙️ Configuration (environment variables)

All settings live in `app/config.py` and can be overridden with environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server URL |
| `VAULTA_MODEL` | `qwen2.5:3b` | Ollama model used for all LLM calls |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for one Ollama response |
| `VAULTA_RETRIEVAL_MODE` | `hybrid` | Knowledge-base search: `hashing`, `bm25`, `semantic` or `hybrid` (see "How retrieval works") |
| `VAULTA_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model for `semantic` / `hybrid` |
| `VAULTA_EMBED_BATCH` | `32` | Texts per embedding request |
| `VAULTA_RETRIEVAL_TOP_K` | `5` | Chunks retrieved per question / investigation (an attached SOP's chunks are taken first) |
| `VAULTA_BACKEND_URL` | `http://127.0.0.1:8000` | Backend URL used by the UI (and by `run.sh` to pick host/port) |
| `VAULTA_UI_REQUEST_TIMEOUT` | `2 × OLLAMA_TIMEOUT + 30` | Seconds the UI waits for the backend |
| `VAULTA_INDEX_DIR` | `data/index` | Where the knowledge-base index is saved |
| `VAULTA_LOG_LEVEL` | `INFO` | Backend log level (`DEBUG`, `INFO`, `WARNING`, ...) |

Data paths are resolved relative to the repo root, so it does not matter which directory you start from:

- `data/documents/` – PDFs auto-indexed into the knowledge base at startup
- `data/spreadsheets/` – demo datasets
- `data/index/` – saved knowledge-base index (generated; not committed)

Example:

```bash
VAULTA_MODEL=qwen2.5:7b OLLAMA_TIMEOUT=600 ./run.sh
```
