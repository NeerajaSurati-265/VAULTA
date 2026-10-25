import json
from typing import Dict, Any, List, Optional

from app.config import RETRIEVAL_TOP_K
from app.main_services.ollama_service import ask_local_ai, MODEL
from app.main_services.pdf_service import extract_text_from_pdf
from app.main_services.data_service import load_dataset, compute_deterministic_analysis
from app.main_services.rag_service import knowledge_base, describe_chunk, chunk_provenance
from app.main_services.verifier_service import verify_output
from app.main_services.report_generator import generate_approval_note


def run_unified_investigation(
    task_prompt: str,
    inspection_file_bytes: Optional[bytes] = None,
    inspection_filename: Optional[str] = None,
    data_file_bytes: Optional[bytes] = None,
    data_filename: Optional[str] = None,
    sop_file_bytes: Optional[bytes] = None,
    sop_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Coordinates multi-agent investigation across Document, Data, and Knowledge/RAG agents,
    followed by cross-source verification and approval note generation.
    """
    execution_trace = []
    evidence: Dict[str, Any] = {
        "inspection_doc": None,
        "data_metrics": None,
        "sop_standards": None,
    }

    # 1. Stage: INVESTIGATION_INITIATED
    attachments = []
    if inspection_filename:
        attachments.append(f"Inspection Doc: {inspection_filename}")
    if data_filename:
        attachments.append(f"Operations Data: {data_filename}")
    if sop_filename:
        attachments.append(f"SOP Manual: {sop_filename}")

    execution_trace.append({
        "stage": "INVESTIGATION_INITIATED",
        "status": "completed",
        "details": {
            "task": task_prompt,
            "attached_sources": attachments if attachments else ["Indexed Knowledge Base"],
            "status": "completed",
        },
    })

    # 2. Stage: DOCUMENT_AGENT (Inspection Report Analysis)
    doc_text = ""
    doc_pages = 0
    if inspection_file_bytes and inspection_filename:
        pdf_res = extract_text_from_pdf(inspection_file_bytes)
        doc_pages = pdf_res.get("pages", 0)
        doc_text = pdf_res.get("text", "")

        evidence["inspection_doc"] = {
            "filename": inspection_filename,
            "pages": doc_pages,
            "text": doc_text[:15000],
        }

        execution_trace.append({
            "stage": "DOCUMENT_AGENT",
            "status": "completed",
            "details": {
                "agent": "DOC_ANALYST",
                "filename": inspection_filename,
                "processor": "PyMuPDF",
                "pages": doc_pages,
                "status": "completed",
            },
        })

    # 3. Stage: DATA_AGENT (Operational Metrics & Outliers)
    statistics = {}
    calculated_results = {}
    if data_file_bytes and data_filename:
        try:
            df = load_dataset(data_file_bytes, data_filename)
            analysis = compute_deterministic_analysis(df)
            statistics = analysis.get("statistics", {})
            calculated_results = analysis.get("calculated_results", {})

            evidence["data_metrics"] = {
                "filename": data_filename,
                "rows": analysis.get("rows", 0),
                "columns": analysis.get("columns", []),
                "numeric_columns": analysis.get("numeric_columns", []),
                "statistics": statistics,
                "highlights": calculated_results.get("highlights", []),
            }

            execution_trace.append({
                "stage": "DATA_AGENT",
                "status": "completed",
                "details": {
                    "agent": "DATA_ANALYST",
                    "filename": data_filename,
                    "processor": "Pandas (Deterministic)",
                    "rows": analysis.get("rows", 0),
                    "columns": len(analysis.get("columns", [])),
                    "status": "completed",
                },
            })
        except Exception as e:
            execution_trace.append({
                "stage": "DATA_AGENT",
                "status": "warning",
                "details": {"error": f"Failed to process dataset: {e}"},
            })

    # 4. Stage: KNOWLEDGE_AGENT (SOP & Technical Standard Retrieval)
    # An attached SOP is the reference the user chose for this investigation, so
    # its best chunks come first and the rest of top_k comes from the whole
    # knowledge base. Ranking the whole KB alone can miss it: SOP continuation
    # pages (e.g. the Pump-402 vibration limits on p.2) do not repeat the
    # equipment name, so a broad task prompt ranks them below other SOPs (U5).
    retrieved_chunks: List[Dict[str, Any]] = []
    if sop_file_bytes and sop_filename:
        knowledge_base.ingest_pdf(sop_file_bytes, sop_filename)
        retrieved_chunks = knowledge_base.retrieve(task_prompt, top_k=RETRIEVAL_TOP_K, doc_names={sop_filename})

    picked = {(c["doc_name"], c["chunk_id"]) for c in retrieved_chunks}
    for c in knowledge_base.retrieve(task_prompt, top_k=RETRIEVAL_TOP_K):
        if len(retrieved_chunks) >= RETRIEVAL_TOP_K:
            break
        if (c["doc_name"], c["chunk_id"]) not in picked:
            retrieved_chunks.append(c)
    evidence["sop_standards"] = {
        "retrieved_chunks": retrieved_chunks,
        "sources": [f"{c['doc_name']} (p.{c['page_number']})" for c in retrieved_chunks],
    }

    execution_trace.append({
        "stage": "KNOWLEDGE_AGENT",
        "status": "completed",
        "details": {
            "agent": "KNOWLEDGE_ANALYST",
            "processor": knowledge_base.get_status()["processor"],
            "retrieval_mode": knowledge_base.retrieval_mode,
            "top_k": RETRIEVAL_TOP_K,
            "chunks_retrieved": len(retrieved_chunks),
            "sources": [describe_chunk(c) for c in retrieved_chunks],
            "chunks": [chunk_provenance(c) for c in retrieved_chunks],
            "status": "completed",
        },
    })

    # 5. Stage: ROOT_CAUSE_SYNTHESIS (Cross-Source Synthesis with Local Qwen 2.5 3B)
    doc_section = doc_text if doc_text else "No inspection document provided."
    data_section = "\n".join(calculated_results.get("highlights", [])) if calculated_results else "No dataset metrics provided."
    
    sop_blocks = []
    for c in retrieved_chunks:
        sop_blocks.append(f"[{c['doc_name']} p.{c['page_number']}]: {c['text'].strip()}")
    sop_section = "\n\n".join(sop_blocks) if sop_blocks else "No reference SOP chunks available."

    synthesis_prompt = f"""You are VAULTA, a sovereign industrial root-cause investigator.
Conduct a thorough, multi-source investigation for the task below by synthesizing:
1. Physical Inspection Findings (Document Evidence)
2. Operational Telemetry & Downtime Trends (Deterministic Data)
3. Standard Operating Procedures & Limit Thresholds (Knowledge Base)

RULES:
- Cross-reference inspection observations against SOP limits (e.g. vibration/temperature thresholds).
- Correlate operational downtime figures with physical wear.
- Base all numerical claims strictly on the provided data highlights.
- Separate documented facts from engineering recommendations.
- Keep the response structured, authoritative, and concise.

INVESTIGATION TASK:
{task_prompt}

EVIDENCE A: PHYSICAL INSPECTION REPORT:
{doc_section[:8000]}

EVIDENCE B: OPERATIONAL DATA HIGHLIGHTS:
{data_section}

EVIDENCE C: SOP THRESHOLDS & TECHNICAL STANDARDS:
{sop_section}

Provide your Root-Cause Analysis, Evidence Correlation, and Corrective Action Plan:"""

    investigation_response = ask_local_ai(synthesis_prompt)

    execution_trace.append({
        "stage": "ROOT_CAUSE_SYNTHESIS",
        "status": "completed",
        "details": {
            "agent": "UNIFIED_INVESTIGATOR",
            "model": MODEL,
            "status": "completed",
        },
    })

    # 6. Stage: CROSS_SOURCE_VERIFICATION
    verification = verify_output(
        response_text=investigation_response,
        route="DOC_ANALYST" if doc_text else ("DATA_ANALYST" if statistics else "KNOWLEDGE_ANALYST"),
        source_text=f"{doc_text}\n{sop_section}",
        statistics=statistics,
        calculated_results=calculated_results,
        retrieved_chunks=retrieved_chunks,
        total_pages=doc_pages,
    )

    execution_trace.append({
        "stage": "CROSS_SOURCE_VERIFICATION",
        "status": "completed",
        "details": {
            "verifier": "VAULTA_VERIFIER",
            "grounding_status": verification.get("grounding_status"),
            "numeric_check": verification.get("numeric_check"),
            "source_check": verification.get("source_check"),
            "warnings": verification.get("warnings"),
            "summary": verification.get("summary"),
            "status": "completed",
        },
    })

    # 7. Stage: APPROVAL_NOTE_GENERATION
    docx_bytes = generate_approval_note(
        task_prompt=task_prompt,
        route="UNIFIED_INVESTIGATION",
        response_text=investigation_response,
        verification=verification,
        filename=f"{inspection_filename or ''} + {data_filename or ''}".strip(" +"),
        pages=doc_pages,
        statistics=statistics,
        calculated_results=calculated_results,
        retrieved_chunks=retrieved_chunks,
        execution_trace=execution_trace,
        model_name=MODEL,
    )

    execution_trace.append({
        "stage": "APPROVAL_NOTE_GENERATION",
        "status": "completed",
        "details": {
            "artifact_type": "DOCX",
            "size_bytes": len(docx_bytes),
            "status": "completed",
        },
    })

    # 8. Stage: OUTPUT_READY
    execution_trace.append({
        "stage": "OUTPUT_READY",
        "status": "completed",
        "details": {
            "status": "completed",
            "local": True,
            "external_calls": 0,
        },
    })

    return {
        "task_prompt": task_prompt,
        "response": investigation_response,
        "evidence": evidence,
        "verification": verification,
        "statistics": statistics,
        "calculated_results": calculated_results,
        "retrieved_chunks": retrieved_chunks,
        # Raw DOCX bytes are deliberately NOT returned: FastAPI cannot JSON-encode
        # binary data (500 error). The UI builds its own DOCX via generate_approval_note.
        "model": MODEL,
        "local": True,
        "external_calls": 0,
        "execution_trace": execution_trace,
    }
