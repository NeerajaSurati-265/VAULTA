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

System Requirements
OS: Ubuntu 22.04+ recommended
Python: 3.10+
RAM: 8 GB minimum, 16 GB recommended
Storage: 10 GB+ free space
CPU: Modern x86_64 processor
GPU: Not required for the current Qwen 2.5 3B setup
Git: Required
Ollama: Required
Docker: Optional

Windows: Can be used through WSL2, but Ubuntu/Linux is recommended for development and deployment.

Installation
1. Clone the Repository
git clone https://github.com/NeerajaSurati-265/VAULTA.git
cd VAULTA
2. Create Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate
3. Install Python Dependencies
pip install -r requirements.txt
4. Install Ollama

Install Ollama on your system, then download the local AI model:

ollama pull qwen2.5:3b

Verify the model:

ollama list

You should see:

qwen2.5:3b
5. Start Ollama

If Ollama is not already running:

ollama serve

VAULTA uses Ollama to run Qwen 2.5 3B locally. No OpenAI/Gemini API key is required for the core runtime.

6. Run VAULTA

From the project root:

source .venv/bin/activate
PYTHONPATH=. streamlit run app/ui.py

Open the local Streamlit URL displayed in the terminal.

Quick Setup

For a fresh Ubuntu machine:

git clone https://github.com/NeerajaSurati-265/VAULTA.git
cd VAULTA

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

ollama pull qwen2.5:3b

PYTHONPATH=. streamlit run app/ui.py
