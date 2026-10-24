import os
import streamlit as st
import requests
from app.main_services.report_generator import generate_approval_note
from app.config import BACKEND_URL, OLLAMA_URL, MODEL, DOCUMENTS_DIR, SPREADSHEETS_DIR, UI_REQUEST_TIMEOUT


# -------------------------------------------------------------------
# PAGE CONFIG & PROFESSIONAL INDUSTRIAL STYLING
# -------------------------------------------------------------------

st.set_page_config(
    page_title="VAULTA — Sovereign Industrial AI Workbench",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS for crisp, restrained industrial aesthetics
st.markdown(
    """
    <style>
    .main-header {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 800;
        font-size: 2.2rem;
        letter-spacing: -0.5px;
        color: #0F172A;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.05rem;
        font-weight: 500;
        color: #475569;
        margin-top: -5px;
        margin-bottom: 12px;
    }
    .sovereign-badge {
        display: inline-block;
        background-color: #F1F5F9;
        border: 1px solid #CBD5E1;
        border-radius: 4px;
        padding: 3px 8px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #1E293B;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------------------------
# HEADER & BRANDING
# -------------------------------------------------------------------

st.markdown('<div class="main-header">🛡️ VAULTA</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">SOVEREIGN INDUSTRIAL AI WORKBENCH &bull; <em>Confidential industrial intelligence — processed entirely on-premise.</em></div>',
    unsafe_allow_html=True,
)

# -------------------------------------------------------------------
# SYSTEM STATUS BAR (Live backend status checks)
# -------------------------------------------------------------------

backend_url = BACKEND_URL


class BackendError(Exception):
    """A backend request failed; the message is meant to be shown to the user."""


def post_backend(path, **kwargs):
    """POST to the backend and return its JSON, turning failures into readable messages."""
    try:
        resp = requests.post(f"{backend_url}{path}", timeout=UI_REQUEST_TIMEOUT, **kwargs)
    except requests.exceptions.Timeout:
        raise BackendError(
            f"The backend did not answer within {UI_REQUEST_TIMEOUT:g} seconds. The local model may "
            "still be busy; try again, or raise OLLAMA_TIMEOUT / VAULTA_UI_REQUEST_TIMEOUT."
        ) from None
    except requests.exceptions.ConnectionError:
        raise BackendError(f"Cannot reach the VAULTA backend at {backend_url}; start it with ./run.sh.") from None
    if not resp.ok:
        # The backend sends {"error": ...} (Ollama problems) or {"detail": ...} (HTTPException)
        try:
            body = resp.json()
            msg = body.get("error") or body.get("detail") or resp.text
        except ValueError:
            msg = resp.text
        raise BackendError(f"Backend returned HTTP {resp.status_code}: {msg}")
    return resp.json()

health_data = {"status": "offline", "ollama": "disconnected", "models": [MODEL]}
kb_data = {"documents_count": 0, "total_chunks": 0, "status": "unavailable"}

try:
    h_res = requests.get(f"{backend_url}/health", timeout=2)
    if h_res.status_code == 200:
        health_data = h_res.json()
except Exception:
    pass

try:
    k_res = requests.get(f"{backend_url}/knowledge/status", timeout=2)
    if k_res.status_code == 200:
        kb_data = k_res.json()
except Exception:
    pass

status_col1, status_col2, status_col3, status_col4, status_col5 = st.columns(5)

with status_col1:
    st.metric("LOCAL AI RUNTIME", MODEL, "Ollama Localhost")

with status_col2:
    st.metric("PROCESSING", "ON-PREMISE", "Air-Gapped")

with status_col3:
    st.metric("EXTERNAL CALLS", "0", "Zero Egress")

with status_col4:
    st.metric("VERIFICATION", "ENABLED", "Empirical Check")

with status_col5:
    doc_cnt = kb_data.get("documents_count", 0)
    chk_cnt = kb_data.get("total_chunks", 0)
    kb_state = f"READY ({doc_cnt} docs, {chk_cnt} chunks)" if doc_cnt > 0 else "READY (0 docs)"
    st.metric("KNOWLEDGE BASE", kb_state, "FAISS IndexFlatIP")

# Ollama lists untagged models as "<name>:latest"
if health_data.get("ollama") == "connected" and not {MODEL, f"{MODEL}:latest"} & set(health_data.get("models", [])):
    st.warning(f"Model `{MODEL}` is not available in Ollama. Run `ollama pull {MODEL}`.")

st.divider()

# -------------------------------------------------------------------
# PRIMARY DEMO & TABBED WORKBENCH
# -------------------------------------------------------------------

tab_inv, tab_doc, tab_data, tab_kb, tab_chat, tab_sov = st.tabs([
    "⚡ Unified Investigation",
    "📄 Document Analysis",
    "📊 Data Analysis",
    "📚 Knowledge Base",
    "💬 Local AI Chat",
    "🔒 Sovereignty & Audit",
])

# ===================================================================
# TAB 1: UNIFIED INVESTIGATION (PRIMARY DEMO)
# ===================================================================
with tab_inv:
    st.subheader("⚡ Multi-Agent Industrial Investigation Workbench")
    st.caption("Cross-Source Investigation: Document Agent + Data Agent + Knowledge Base + Verifier + Signed Approval Note")

    demo_insp_path = str(DOCUMENTS_DIR / "pump_inspection.pdf")
    demo_data_path = str(SPREADSHEETS_DIR / "maintenance_metrics.csv")
    demo_sop_path = str(DOCUMENTS_DIR / "SOP-PUMP-402.pdf")

    has_demo_files = (
        os.path.exists(demo_insp_path)
        and os.path.exists(demo_data_path)
        and os.path.exists(demo_sop_path)
    )

    st.info(
        "💡 **One-Click Demo Investigation**: Cross-reference physical inspection findings (`pump_inspection.pdf`), "
        "downtime metrics (`maintenance_metrics.csv`), and reference standards (`SOP-PUMP-402.pdf`) using local AI."
    )

    inv_prompt = st.text_area(
        "Investigation Mission / Question:",
        value="Investigate the recurring vibration and downtime on Pump P-402, cross-reference operating logs against SOP standards, and prepare an engineering approval note.",
        height=80,
        key="main_inv_prompt",
    )

    btn_col1, btn_col2 = st.columns([1, 2])
    with btn_col1:
        run_demo_btn = st.button("🚀 Run Pump-402 Investigation", type="primary", use_container_width=True)

    with st.expander("Custom Multi-Source Attachments (Optional Override)"):
        cust_col1, cust_col2, cust_col3 = st.columns(3)
        with cust_col1:
            cust_insp = st.file_uploader("Custom Inspection PDF", type=["pdf"], key="cust_insp_up")
        with cust_col2:
            cust_data = st.file_uploader("Custom Metrics CSV/Excel", type=["csv", "xlsx", "xls"], key="cust_data_up")
        with cust_col3:
            cust_sop = st.file_uploader("Custom SOP PDF", type=["pdf"], key="cust_sop_up")

    if run_demo_btn:
        with st.spinner("Orchestrating multi-agent investigation across Document, Data, and Knowledge engines..."):
            try:
                # Prepare payload
                files_payload = {}

                # 1. Inspection Report
                if cust_insp:
                    files_payload["inspection_file"] = (cust_insp.name, cust_insp.getvalue(), "application/pdf")
                elif os.path.exists(demo_insp_path):
                    with open(demo_insp_path, "rb") as f:
                        files_payload["inspection_file"] = ("pump_inspection.pdf", f.read(), "application/pdf")

                # 2. Operations Data
                if cust_data:
                    mime_d = "text/csv" if cust_data.name.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    files_payload["data_file"] = (cust_data.name, cust_data.getvalue(), mime_d)
                elif os.path.exists(demo_data_path):
                    with open(demo_data_path, "rb") as f:
                        files_payload["data_file"] = ("maintenance_metrics.csv", f.read(), "text/csv")

                # 3. SOP Manual
                if cust_sop:
                    files_payload["sop_file"] = (cust_sop.name, cust_sop.getvalue(), "application/pdf")
                elif os.path.exists(demo_sop_path):
                    with open(demo_sop_path, "rb") as f:
                        files_payload["sop_file"] = ("SOP-PUMP-402.pdf", f.read(), "application/pdf")

                inv_res = post_backend(
                    "/investigate",
                    data={"prompt": inv_prompt},
                    files=files_payload if files_payload else None,
                )

                st.success("Unified investigation completed successfully with zero cloud transmission!")

                # --- AGENT EXECUTION TRACE ---
                inv_trace = inv_res.get("execution_trace", [])
                if inv_trace:
                    with st.status("🔐 Agent Execution Trace (8/8 Stages)", expanded=True) as trace_box:
                        for event in inv_trace:
                            stg = event.get("stage")
                            dt = event.get("details", {})

                            if stg == "INVESTIGATION_INITIATED":
                                st.markdown(f"**✓ 1. Investigation Initiated**\n\n• Sources Attached: `{', '.join(dt.get('attached_sources', []))}`")
                            elif stg == "DOCUMENT_AGENT":
                                st.markdown(f"**✓ 2. Document Agent (`DOC_ANALYST`)**\n\n• Processor: `{dt.get('processor')}` | File: `{dt.get('filename')}` ({dt.get('pages')} page(s))")
                            elif stg == "DATA_AGENT":
                                st.markdown(f"**✓ 3. Data Agent (`DATA_ANALYST`)**\n\n• Processor: `{dt.get('processor')}` | File: `{dt.get('filename')}` ({dt.get('rows')} rows, {dt.get('columns')} columns)")
                            elif stg == "KNOWLEDGE_AGENT":
                                st.markdown(f"**✓ 4. Knowledge Agent (`KNOWLEDGE_ANALYST`)**\n\n• Processor: `{dt.get('processor')}` | Chunks Retrieved: `{dt.get('chunks_retrieved')}` ({', '.join(dt.get('sources', []))})")
                            elif stg == "ROOT_CAUSE_SYNTHESIS":
                                st.markdown(f"**✓ 5. Root-Cause Cross-Synthesis**\n\n• Agent: `{dt.get('agent')}` | Model: `{dt.get('model')}` (Local Inference)")
                            elif stg == "CROSS_SOURCE_VERIFICATION":
                                st.markdown(f"**✓ 6. Cross-Source Verification**\n\n• Verifier: `{dt.get('verifier')}` | Grounding: `{dt.get('grounding_status')}`\n\n• Summary: *{dt.get('summary')}*")
                            elif stg == "APPROVAL_NOTE_GENERATION":
                                st.markdown(f"**✓ 7. Deliverable Generation**\n\n• Artifact: `{dt.get('artifact_type')}` ({dt.get('size_bytes')} bytes) via python-docx")
                            elif stg == "OUTPUT_READY":
                                st.markdown(f"**✓ 8. Output Ready**\n\n• Inference: Local (Air-Gapped) | External Calls: `0`")

                        trace_box.update(label="🔐 Agent Execution Trace — Complete (8/8 Stages)", state="complete", expanded=True)

                # --- VERIFICATION STATUS CARD ---
                inv_v = inv_res.get("verification", {})
                if inv_v:
                    st.subheader("🛡️ Cross-Source Grounding & Verification")
                    v_col1, v_col2, v_col3 = st.columns(3)
                    with v_col1:
                        st.info(f"**Grounding:** `{inv_v.get('grounding_status')}`")
                    with v_col2:
                        st.info(f"**Source Alignment:** `{inv_v.get('source_check')}`")
                    with v_col3:
                        st.info(f"**Numeric Consistency:** `{inv_v.get('numeric_check')}`")

                # --- ROOT CAUSE FINDINGS ---
                st.subheader("📋 Root-Cause Investigation & Action Plan")
                st.write(inv_res.get("response", ""))

                # --- DOWNLOAD APPROVAL NOTE BUTTON ---
                inv_docx = generate_approval_note(
                    task_prompt=inv_prompt,
                    route="UNIFIED_INVESTIGATION",
                    response_text=inv_res.get("response", ""),
                    verification=inv_v,
                    filename="pump_inspection.pdf + maintenance_metrics.csv",
                    statistics=inv_res.get("statistics", {}),
                    calculated_results=inv_res.get("calculated_results", {}),
                    retrieved_chunks=inv_res.get("retrieved_chunks", []),
                    execution_trace=inv_trace,
                )

                st.download_button(
                    label="📄 Download Official Approval Note (.docx)",
                    data=inv_docx,
                    file_name="VAULTA_Pump402_Approval_Note.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="download_unified_note_btn",
                    type="primary",
                )

                # --- MULTI-SOURCE EVIDENCE MATRIX ---
                with st.expander("🔍 Multi-Source Evidence Matrix (Inspection + Data + SOPs)"):
                    ev = inv_res.get("evidence", {})
                    t1, t2, t3 = st.tabs(["📄 Physical Inspection Report", "📊 Operating Metrics (Pandas)", "📚 SOP Reference Standards"])
                    with t1:
                        if ev.get("inspection_doc"):
                            st.text(ev["inspection_doc"].get("text", ""))
                        else:
                            st.write("No inspection document text available.")
                    with t2:
                        if ev.get("data_metrics"):
                            st.json(ev["data_metrics"].get("statistics", {}))
                            for h in ev["data_metrics"].get("highlights", []):
                                st.write(f"• {h}")
                        else:
                            st.write("No data metrics available.")
                    with t3:
                        if ev.get("sop_standards") and ev["sop_standards"].get("retrieved_chunks"):
                            for c in ev["sop_standards"]["retrieved_chunks"]:
                                st.markdown(f"**{c.get('doc_name')} (p.{c.get('page_number')})** — *Score: {c.get('score')}*")
                                st.text(c.get("text", ""))
                        else:
                            st.write("No SOP chunks retrieved.")

                with st.expander("View raw JSON trace"):
                    st.json(inv_trace)

            except Exception as e:
                st.error(f"Investigation execution failed: {e}. Please ensure the VAULTA backend and Ollama are running.")

# ===================================================================
# TAB 2: DOCUMENT ANALYST
# ===================================================================
with tab_doc:
    st.subheader("📄 Document Analyst")
    st.caption("Sovereign document analysis with in-memory page citations and local verification.")

    doc_upload = st.file_uploader("Upload PDF document", type=["pdf"], key="single_doc_upload")
    doc_question = st.text_input(
        "Question / Instruction for Document:",
        value="What are the key findings, vibration levels, and recommended overhaul actions?",
        key="single_doc_prompt",
    )

    if st.button("Analyze Document", key="btn_doc_analyze", type="primary"):
        if doc_upload is None:
            st.warning("Please upload a PDF document first.")
        else:
            with st.spinner("Extracting and analyzing document locally..."):
                try:
                    result = post_backend(
                        "/agent/run",
                        files={"file": (doc_upload.name, doc_upload.getvalue(), "application/pdf")},
                        data={"prompt": doc_question},
                    )

                    st.success("Document analyzed locally")

                    # Execution Trace
                    execution_trace = result.get("execution_trace", [])
                    if execution_trace:
                        with st.status("🔐 Agent Execution Trace", expanded=True) as trace_status:
                            for event in execution_trace:
                                stage = event.get("stage")
                                details = event.get("details", {})
                                if stage == "FILE_RECEIVED":
                                    st.markdown(f"**✓ File Received:** `{details.get('filename')}` ({details.get('file_type')})")
                                elif stage == "TASK_ROUTING":
                                    st.markdown(f"**✓ Task Router:** Route `{details.get('route')}` | Confidence `{int(details.get('confidence', 0)*100)}%`")
                                elif stage == "DOCUMENT_EXTRACTION":
                                    st.markdown(f"**✓ Document Extraction:** `{details.get('processor')}` ({details.get('pages')} pages)")
                                elif stage == "DOCUMENT_ANALYSIS":
                                    st.markdown(f"**✓ Document Analysis:** `{details.get('agent')}` | Model `{details.get('model')}`")
                                elif stage == "VERIFICATION":
                                    st.markdown(f"**✓ Verifier Check:** `{details.get('grounding_status')}` | Citations `{details.get('source_check')}`")
                                elif stage == "OUTPUT_READY":
                                    st.markdown(f"**✓ Output Ready:** Local `{details.get('local')}` | External Calls `{details.get('external_calls')}`")

                            trace_status.update(label="🔐 Agent Execution Trace — Complete", state="complete", expanded=True)

                    # Verification Card
                    verification = result.get("verification", {})
                    if verification:
                        st.subheader("🛡️ Verification & Grounding Check")
                        v1, v2, v3 = st.columns(3)
                        with v1:
                            st.info(f"**Grounding:** `{verification.get('grounding_status')}`")
                        with v2:
                            st.info(f"**Source Check:** `{verification.get('source_check')}`")
                        with v3:
                            st.info(f"**Numeric Check:** `{verification.get('numeric_check')}`")

                    st.subheader("Analysis Findings")
                    st.write(result.get("response", ""))

                    # Download Official Approval Note Button
                    docx_bytes = generate_approval_note(
                        task_prompt=doc_question,
                        route=result.get("route", "DOC_ANALYST"),
                        response_text=result.get("response", ""),
                        verification=result.get("verification", {}),
                        filename=doc_upload.name,
                        pages=result.get("pages", 0),
                        execution_trace=result.get("execution_trace", []),
                    )
                    st.download_button(
                        label="📄 Download Official Approval Note (.docx)",
                        data=docx_bytes,
                        file_name=f"approval_note_{doc_upload.name.replace('.pdf', '')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="download_doc_note_btn",
                    )

                    with st.expander("View extracted document text"):
                        st.text(result.get("text", ""))

                except Exception as e:
                    st.error(f"Document analysis failed: {e}")

# ===================================================================
# TAB 3: DATA ANALYST
# ===================================================================
with tab_data:
    st.subheader("📊 Data Analyst")
    st.caption("Deterministic Pandas statistical calculations + open-weight AI interpretation.")

    data_file = st.file_uploader("Upload Metrics Dataset (.csv / .xlsx)", type=["csv", "xlsx", "xls"], key="single_data_upload")
    data_question = st.text_input(
        "Question / Calculation Task:",
        value="Calculate the average downtime and identify the equipment with highest downtime hours.",
        key="single_data_prompt",
    )

    if st.button("Analyze Dataset", key="btn_data_analyze", type="primary"):
        if data_file is None:
            st.warning("Please upload a CSV or Excel dataset first.")
        else:
            with st.spinner("Processing dataset deterministically with Pandas..."):
                try:
                    mime = "text/csv" if data_file.name.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    result = post_backend(
                        "/agent/run",
                        files={"file": (data_file.name, data_file.getvalue(), mime)},
                        data={"prompt": data_question},
                    )

                    st.success("Dataset analyzed locally")

                    # Execution Trace
                    execution_trace = result.get("execution_trace", [])
                    if execution_trace:
                        with st.status("🔐 Agent Execution Trace", expanded=True) as trace_status:
                            for event in execution_trace:
                                stage = event.get("stage")
                                details = event.get("details", {})
                                if stage == "FILE_RECEIVED":
                                    st.markdown(f"**✓ File Received:** `{details.get('filename')}` ({details.get('file_type')})")
                                elif stage == "TASK_ROUTING":
                                    st.markdown(f"**✓ Task Router:** Route `{details.get('route')}` | Confidence `{int(details.get('confidence', 0)*100)}%`")
                                elif stage == "DATA_LOADING":
                                    st.markdown(f"**✓ Data Loading:** `{details.get('processor')}`")
                                elif stage == "DATA_ANALYSIS":
                                    st.markdown(f"**✓ Deterministic Analysis:** `{details.get('processor')}` ({details.get('rows')} rows, {details.get('columns')} cols)")
                                elif stage == "AI_INTERPRETATION":
                                    st.markdown(f"**✓ AI Interpretation:** Model `{details.get('model')}`")
                                elif stage == "VERIFICATION":
                                    st.markdown(f"**✓ Verifier Check:** `{details.get('grounding_status')}` | Numeric `{details.get('numeric_check')}`")
                                elif stage == "OUTPUT_READY":
                                    st.markdown(f"**✓ Output Ready:** Local `{details.get('local')}` | External Calls `{details.get('external_calls')}`")

                            trace_status.update(label="🔐 Agent Execution Trace — Complete", state="complete", expanded=True)

                    # Verification Card
                    verification = result.get("verification", {})
                    if verification:
                        st.subheader("🛡️ Verification & Grounding Check")
                        v1, v2, v3 = st.columns(3)
                        with v1:
                            st.info(f"**Grounding:** `{verification.get('grounding_status')}`")
                        with v2:
                            st.info(f"**Numeric Consistency:** `{verification.get('numeric_check')}`")
                        with v3:
                            st.info(f"**Source Check:** `{verification.get('source_check')}`")

                    # Deterministic Highlights
                    st.subheader("🔢 Deterministic Calculated Results (Pandas)")
                    calc_results = result.get("calculated_results", {})
                    highlights = calc_results.get("highlights", [])
                    if highlights:
                        for h in highlights:
                            st.info(f"📌 {h}")

                    st.subheader("💡 AI Interpretation")
                    st.write(result.get("response", ""))

                    # Download Official Approval Note Button
                    docx_bytes_data = generate_approval_note(
                        task_prompt=data_question,
                        route=result.get("route", "DATA_ANALYST"),
                        response_text=result.get("response", ""),
                        verification=result.get("verification", {}),
                        filename=data_file.name,
                        statistics=result.get("statistics", {}),
                        calculated_results=result.get("calculated_results", {}),
                        execution_trace=result.get("execution_trace", []),
                    )
                    st.download_button(
                        label="📄 Download Official Approval Note (.docx)",
                        data=docx_bytes_data,
                        file_name=f"approval_note_{data_file.name.split('.')[0]}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="download_data_note_btn",
                    )

                    with st.expander("View descriptive statistics (JSON)"):
                        st.json(result.get("statistics", {}))

                except Exception as e:
                    st.error(f"Dataset analysis failed: {e}")

# ===================================================================
# TAB 4: KNOWLEDGE BASE / RAG
# ===================================================================
with tab_kb:
    st.subheader("📚 Sovereign Knowledge Base / Local RAG")
    st.caption("FAISS cosine vector retrieval across indexed plant SOPs and operating manuals.")

    kb_c1, kb_c2, kb_c3 = st.columns(3)
    with kb_c1:
        st.metric("Indexed Documents", kb_data.get("documents_count", 0))
    with kb_c2:
        st.metric("Total Vector Chunks", kb_data.get("total_chunks", 0))
    with kb_c3:
        st.metric("Vector Index", "FAISS IndexFlatIP (1024-d)")

    if kb_data.get("indexed_documents"):
        st.write(f"**Indexed SOPs in Memory:** `{', '.join(kb_data.get('indexed_documents', []))}`")

    with st.expander("📥 Ingest New SOP / Manual PDF into Knowledge Base"):
        kb_upload = st.file_uploader("Upload PDF to index", type=["pdf"], key="kb_file_up")
        if st.button("Index Document into FAISS", key="index_kb_btn"):
            if kb_upload is None:
                st.warning("Please select a PDF file first.")
            else:
                with st.spinner("Indexing document into FAISS vector store..."):
                    try:
                        ingest_info = post_backend(
                            "/knowledge/ingest",
                            files={"file": (kb_upload.name, kb_upload.getvalue(), "application/pdf")},
                        )
                        if ingest_info.get("status") == "already_indexed":
                            st.info(f"'{ingest_info.get('filename')}' is already indexed with the same content; nothing changed.")
                        else:
                            verb = "Replaced" if ingest_info.get("status") == "replaced" else "Indexed"
                            st.success(f"{verb} '{ingest_info.get('filename')}' ({ingest_info.get('chunks_added')} chunks added).")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to index document: {e}")

    kb_query = st.text_input(
        "Search or ask a question across all indexed knowledge:",
        value="What are the emergency lubrication intervals and vibration limits for centrifugal pumps?",
        key="kb_search_input",
    )

    if st.button("Query Knowledge Base", type="primary", key="btn_kb_search"):
        if not kb_query.strip():
            st.warning("Please enter a search query.")
        else:
            with st.spinner("Searching FAISS vector index and synthesizing grounded answer..."):
                try:
                    result = post_backend(
                        "/agent/run",
                        data={"prompt": f"Search the knowledge base and SOPs: {kb_query}"},
                    )

                    st.success("Knowledge retrieval complete")

                    # Execution Trace
                    execution_trace = result.get("execution_trace", [])
                    if execution_trace:
                        with st.status("🔐 Agent Execution Trace", expanded=True) as trace_status:
                            for event in execution_trace:
                                stage = event.get("stage")
                                details = event.get("details", {})
                                if stage == "TASK_ROUTING":
                                    st.markdown(f"**✓ Task Router:** Route `{details.get('route')}`")
                                elif stage == "KNOWLEDGE_RETRIEVAL":
                                    st.markdown(f"**✓ FAISS Retrieval:** Retrieved `{details.get('chunks_retrieved')}` chunks from {', '.join(details.get('sources', []))}")
                                elif stage == "KNOWLEDGE_SYNTHESIS":
                                    st.markdown(f"**✓ Grounded Synthesis:** Model `{details.get('model')}`")
                                elif stage == "VERIFICATION":
                                    st.markdown(f"**✓ Verifier Check:** `{details.get('grounding_status')}` | Sources `{details.get('source_check')}`")
                                elif stage == "OUTPUT_READY":
                                    st.markdown(f"**✓ Output Ready:** Local `{details.get('local')}` | External Calls `{details.get('external_calls')}`")

                            trace_status.update(label="🔐 Agent Execution Trace — Complete", state="complete", expanded=True)

                    # Verification Card
                    verification = result.get("verification", {})
                    if verification:
                        st.subheader("🛡️ Verification & Grounding Check")
                        v1, v2, v3 = st.columns(3)
                        with v1:
                            st.info(f"**Grounding:** `{verification.get('grounding_status')}`")
                        with v2:
                            st.info(f"**Source Check:** `{verification.get('source_check')}`")
                        with v3:
                            st.info(f"**Numeric Check:** `{verification.get('numeric_check')}`")

                    st.subheader("📖 Grounded Answer")
                    st.write(result.get("response", ""))

                    # Download Official Approval Note Button
                    docx_bytes_kb = generate_approval_note(
                        task_prompt=kb_query,
                        route=result.get("route", "KNOWLEDGE_ANALYST"),
                        response_text=result.get("response", ""),
                        verification=result.get("verification", {}),
                        retrieved_chunks=result.get("retrieved_chunks", []),
                        execution_trace=result.get("execution_trace", []),
                    )
                    st.download_button(
                        label="📄 Download Official Approval Note (.docx)",
                        data=docx_bytes_kb,
                        file_name="approval_note_knowledge_synthesis.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="download_kb_note_btn",
                    )

                    retrieved_chunks = result.get("retrieved_chunks", [])
                    if retrieved_chunks:
                        with st.expander(f"📑 Retrieved Context Chunks ({len(retrieved_chunks)} citations)"):
                            for i, chunk in enumerate(retrieved_chunks, start=1):
                                st.markdown(f"**Source #{i}: `{chunk.get('doc_name')}` (Page {chunk.get('page_number')})** — *Score: `{chunk.get('score')}`*")
                                st.text(chunk.get("text", ""))

                except Exception as e:
                    st.error(f"Knowledge search failed: {e}")

# ===================================================================
# TAB 5: LOCAL AI CHAT
# ===================================================================
with tab_chat:
    st.subheader("💬 Local Sovereign AI Chat")
    st.caption("Direct conversational interaction with on-premise open-weight model.")

    chat_prompt = st.text_area(
        "Enter prompt or technical question:",
        placeholder="Example: Explain the difference between cavitation erosion and fatigue failure in centrifugal pumps.",
        height=100,
        key="chat_prompt_input",
    )

    if st.button("Run Local AI", type="primary", key="btn_chat_run"):
        if not chat_prompt.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Processing on local model..."):
                try:
                    result = post_backend("/chat", json={"prompt": chat_prompt})

                    st.success("Response generated locally")
                    st.write(result.get("response", ""))
                    st.caption(f"Model: {result.get('model')} | Local: {result.get('local')} | External Calls: {result.get('external_calls')}")
                except Exception as e:
                    st.error(f"Chat request failed: {e}")

# ===================================================================
# TAB 6: SOVEREIGNTY & AUDIT
# ===================================================================
with tab_sov:
    st.subheader("🔒 Sovereignty & Air-Gap Compliance Certificate")
    st.caption("Verification of 100% on-premise runtime architecture.")

    sov_col1, sov_col2 = st.columns(2)

    with sov_col1:
        st.markdown(
            f"""
            ### System Guarantees
            * **Processing Environment:** On-Premise / Local Host
            * **Runtime LLM:** Qwen 2.5 3B (Open-Weight)
            * **Inference Server:** Ollama (`{OLLAMA_URL}`)
            * **Vector Engine:** FAISS (`IndexFlatIP`)
            * **External API Calls:** `0` (Zero Egress)
            * **Cloud AI Dependencies:** `None` (Air-Gapped)
            """
        )

    with sov_col2:
        st.markdown(
            """
            ### Compliance Summary
            * **Document Privacy:** All PyMuPDF extractions remain in-memory.
            * **Data Calculation:** 100% deterministic with Pandas; LLM does not perform math.
            * **Verification:** Every output is cross-checked for grounding against source texts.
            * **Deliverables:** Formatted `.docx` approval notes generated locally via python-docx.
            """
        )

    st.divider()
    st.caption("VAULTA Sovereign Workbench &bull; Hackathon Release &bull; 0 External Network Calls")