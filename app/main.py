import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import LOG_LEVEL, RETRIEVAL_TOP_K

# Configure logging before importing the services: the knowledge base is built
# (and logs its ingests) at import time.
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("vaulta")

from app.main_services.ollama_service import (
    MODEL,
    OllamaError,
    get_models,
    ask_local_ai,
)

from app.main_services.pdf_service import (
    extract_text_from_pdf,
    build_document_prompt,
)

from app.main_services.data_service import (
    load_dataset,
    compute_deterministic_analysis,
    build_data_interpretation_prompt,
)

from app.main_services.rag_service import knowledge_base, describe_chunk, chunk_provenance
from app.main_services.verifier_service import verify_output
from app.main_services.report_generator import generate_approval_note
from app.main_services.investigation_service import run_unified_investigation

from app.agents import (

    TaskRouter,
    DOC_ANALYST,
    DATA_ANALYST,
    KNOWLEDGE_ANALYST,
    GENERAL_AI,
)

app = FastAPI(title="VAULTA", version="0.2.0")


@app.exception_handler(OllamaError)
async def ollama_error_handler(request: Request, exc: OllamaError):
    # 503 = a dependency (Ollama) is unavailable; the message says how to fix it
    logger.error("Ollama error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"error": str(exc)})


class ChatRequest(BaseModel):
    prompt: str


class KnowledgeQueryRequest(BaseModel):
    query: str
    top_k: int = RETRIEVAL_TOP_K


class ApprovalNoteRequest(BaseModel):
    task_prompt: str
    route: str
    response_text: str
    verification: Optional[Dict[str, Any]] = None
    filename: Optional[str] = None
    pages: int = 0
    statistics: Optional[Dict[str, Any]] = None
    calculated_results: Optional[Dict[str, Any]] = None
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None
    model_name: str = MODEL





@app.get("/")
def root():
    return {
        "name": "VAULTA",
        "status": "online",
        "ai": "local Ollama",
        "model": MODEL,
        "external_calls": 0,
    }


@app.get("/health")
def health():
    try:
        models = get_models()

        return {
            "status": "healthy",
            "ollama": "connected",
            "models": [m["name"] for m in models],
            "external_calls": 0,
        }

    except Exception as e:
        return {
            "status": "degraded",
            "ollama": "unavailable",
            "error": str(e),
            "external_calls": 0,
        }


@app.post("/chat")
def chat(request: ChatRequest):
    answer = ask_local_ai(request.prompt)

    return {
        "response": answer,
        "model": MODEL,
        "local": True,
        "external_calls": 0,
    }

# Several endpoints are `async` (they await file uploads), so any slow blocking
# call (Ollama, PDF parsing, indexing) goes through run_in_threadpool. Calling it
# directly would freeze the event loop and every other request, /health included.

@app.post("/analyze-pdf")
async def analyze_pdf(
    file: UploadFile = File(...),
    question: str = "Summarize the key findings in this document."
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    file_bytes = await file.read()

    result = await run_in_threadpool(extract_text_from_pdf, file_bytes)

    if not result["text"].strip():
        return {
            "filename": file.filename,
            "pages": result["pages"],
            "response": "No selectable text was found in this PDF.",
            "model": MODEL,
            "local": True,
            "external_calls": 0,
        }

    document_text = result["text"][:30000]

    prompt = build_document_prompt(
        document_text,
        question,
    )

    answer = await run_in_threadpool(ask_local_ai, prompt)

    return {
        "filename": file.filename,
        "pages": result["pages"],
        "text": document_text,
        "response": answer,
        "model": MODEL,
        "local": True,
        "external_calls": 0,
    }


@app.get("/knowledge/status")
def get_knowledge_status():
    return knowledge_base.get_status()


@app.post("/knowledge/ingest")
async def ingest_knowledge_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF documents are supported for knowledge base ingestion."
        )
    file_bytes = await file.read()
    res = await run_in_threadpool(knowledge_base.ingest_pdf, file_bytes, file.filename)
    return res


@app.post("/knowledge/query")
def query_knowledge(request: KnowledgeQueryRequest):
    return knowledge_base.query(request.query, top_k=request.top_k)


@app.post("/reports/approval-note")
def create_approval_note(request: ApprovalNoteRequest):
    docx_bytes = generate_approval_note(
        task_prompt=request.task_prompt,
        route=request.route,
        response_text=request.response_text,
        verification=request.verification,
        filename=request.filename,
        pages=request.pages,
        statistics=request.statistics,
        calculated_results=request.calculated_results,
        retrieved_chunks=request.retrieved_chunks,
        model_name=request.model_name,
    )
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=approval_note_{request.route.lower()}.docx"
        },
    )


@app.post("/investigate")
async def investigate_task(
    prompt: str = Form(...),
    inspection_file: Optional[UploadFile] = File(None),
    data_file: Optional[UploadFile] = File(None),
    sop_file: Optional[UploadFile] = File(None),
):
    insp_bytes = await inspection_file.read() if inspection_file else None
    insp_name = inspection_file.filename if inspection_file else None

    d_bytes = await data_file.read() if data_file else None
    d_name = data_file.filename if data_file else None

    s_bytes = await sop_file.read() if sop_file else None
    s_name = sop_file.filename if sop_file else None

    result = await run_in_threadpool(
        run_unified_investigation,
        task_prompt=prompt,
        inspection_file_bytes=insp_bytes,
        inspection_filename=insp_name,
        data_file_bytes=d_bytes,
        data_filename=d_name,
        sop_file_bytes=s_bytes,
        sop_filename=s_name,
    )
    return result


@app.post("/agent/run")


async def agent_run(
    prompt: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    filename = file.filename if file and file.filename else None
    if filename:
        low = filename.lower()
        if low.endswith(".pdf"):
            file_type = "PDF"
        elif low.endswith(".csv"):
            file_type = "CSV"
        elif low.endswith((".xlsx", ".xls")):
            file_type = "Excel"
        else:
            file_type = file.content_type if (file and file.content_type) else "Unknown"
    else:
        file_type = None

    execution_trace = []

    # 1. FILE_RECEIVED
    if file and filename:
        execution_trace.append({
            "stage": "FILE_RECEIVED",
            "status": "completed",
            "details": {
                "filename": filename,
                "file_type": file_type or "Unknown",
                "status": "completed",
            },
        })

    # 2. TASK_ROUTING
    routing_result = await run_in_threadpool(TaskRouter.route, prompt=prompt, filename=filename, file_type=file_type)
    route = routing_result.get("route", GENERAL_AI)
    confidence = routing_result.get("confidence", 1.0)
    reason = routing_result.get("reason", "")

    # The LLM router only sees the filename as text and can pick an agent that
    # cannot handle the attached file, so the file extension has the final say.
    if filename:
        low = filename.lower()
        corrected_route = None
        if low.endswith((".csv", ".xlsx", ".xls")) and route != DATA_ANALYST:
            corrected_route = DATA_ANALYST
        elif low.endswith(".pdf") and route not in (DOC_ANALYST, KNOWLEDGE_ANALYST):
            corrected_route = DOC_ANALYST
        if corrected_route:
            reason = f"{reason} [Route corrected from {route} to {corrected_route} based on the attached file type.]".strip()
            route = corrected_route

    execution_trace.append({
        "stage": "TASK_ROUTING",
        "status": "completed",
        "details": {
            "route": route,
            "confidence": confidence,
            "model": MODEL,
            "reason": reason,
            "status": "completed",
        },
    })

    pages = 0
    document_text = ""
    response_text = ""
    rows = 0
    columns = []
    numeric_columns = []
    statistics = {}
    calculated_results = {}
    retrieved_chunks = []

    try:
        if route == DOC_ANALYST:
            if file and filename and filename.lower().endswith(".pdf"):
                file_bytes = await file.read()
                pdf_result = await run_in_threadpool(extract_text_from_pdf, file_bytes)
                pages = pdf_result.get("pages", 0)
                document_text = pdf_result.get("text", "")

                if not document_text.strip():
                    execution_trace.append({
                        "stage": "DOCUMENT_EXTRACTION",
                        "status": "failed",
                        "details": {
                            "processor": "PyMuPDF",
                            "pages": pages,
                            "status": "No selectable text found in PDF",
                        },
                    })
                    response_text = "No selectable text was found in this PDF."
                else:
                    # 3. DOCUMENT_EXTRACTION
                    execution_trace.append({
                        "stage": "DOCUMENT_EXTRACTION",
                        "status": "completed",
                        "details": {
                            "processor": "PyMuPDF",
                            "pages": pages,
                            "status": "completed",
                        },
                    })

                    # 4. DOCUMENT_ANALYSIS
                    execution_trace.append({
                        "stage": "DOCUMENT_ANALYSIS",
                        "status": "completed",
                        "details": {
                            "agent": "DOC_ANALYST",
                            "model": MODEL,
                            "status": "completed",
                        },
                    })

                    doc_prompt = build_document_prompt(document_text[:30000], prompt)
                    response_text = await run_in_threadpool(ask_local_ai, doc_prompt)

            elif file and filename:
                response_text = f"Document analysis currently supports PDF files. Received: {filename}"
            else:
                response_text = await run_in_threadpool(ask_local_ai, prompt)

        elif route == DATA_ANALYST:
            if file and filename:
                file_bytes = await file.read()
                df = load_dataset(file_bytes, filename)

                execution_trace.append({
                    "stage": "DATA_LOADING",
                    "status": "completed",
                    "details": {
                        "filename": filename,
                        "file_type": file_type or "Unknown",
                        "processor": "Pandas",
                        "status": "completed",
                    },
                })

                analysis = compute_deterministic_analysis(df)
                rows = analysis.get("rows", 0)
                columns = analysis.get("columns", [])
                numeric_columns = analysis.get("numeric_columns", [])
                statistics = analysis.get("statistics", {})
                calculated_results = analysis.get("calculated_results", {})

                execution_trace.append({
                    "stage": "DATA_ANALYSIS",
                    "status": "completed",
                    "details": {
                        "processor": "Pandas",
                        "rows": rows,
                        "columns": len(columns),
                        "numeric_columns": numeric_columns,
                        "status": "completed",
                    },
                })

                data_prompt = build_data_interpretation_prompt(
                    question=prompt,
                    filename=filename,
                    rows=rows,
                    columns=columns,
                    numeric_columns=numeric_columns,
                    statistics=statistics,
                    highlights=calculated_results.get("highlights", []),
                )

                execution_trace.append({
                    "stage": "AI_INTERPRETATION",
                    "status": "completed",
                    "details": {
                        "agent": "DATA_ANALYST",
                        "model": MODEL,
                        "status": "completed",
                    },
                })

                response_text = await run_in_threadpool(ask_local_ai, data_prompt)

            else:
                response_text = "DATA_ANALYST route selected, but no dataset file (CSV/XLSX) was provided."

        elif route == KNOWLEDGE_ANALYST:
            # If user uploaded a new PDF along with their query, ingest it
            if file and filename and filename.lower().endswith(".pdf"):
                file_bytes = await file.read()
                await run_in_threadpool(knowledge_base.ingest_pdf, file_bytes, filename)
                execution_trace.append({
                    "stage": "DOCUMENT_INGESTION",
                    "status": "completed",
                    "details": {
                        "filename": filename,
                        "processor": "FAISS + Local Embeddings",
                        "status": "completed",
                    },
                })

            # query() retrieves and synthesizes in one pass; reuse its chunks for the trace
            kb_res = await run_in_threadpool(knowledge_base.query, prompt, top_k=RETRIEVAL_TOP_K)
            response_text = kb_res.get("response", "")
            retrieved = kb_res.get("retrieved_chunks", [])
            retrieved_chunks = retrieved

            execution_trace.append({
                "stage": "KNOWLEDGE_RETRIEVAL",
                "status": "completed",
                "details": {
                    "processor": knowledge_base.get_status()["processor"],
                    "retrieval_mode": knowledge_base.retrieval_mode,
                    "top_k": RETRIEVAL_TOP_K,
                    "chunks_retrieved": len(retrieved),
                    "sources": [describe_chunk(c) for c in retrieved],
                    "chunks": [chunk_provenance(c) for c in retrieved],
                    "status": "completed",
                },
            })

            execution_trace.append({
                "stage": "KNOWLEDGE_SYNTHESIS",
                "status": "completed",
                "details": {
                    "agent": "KNOWLEDGE_ANALYST",
                    "model": MODEL,
                    "status": "completed",
                },
            })

        else:
            response_text = await run_in_threadpool(ask_local_ai, prompt)

        # VERIFICATION
        verification_result = verify_output(
            response_text=response_text,
            route=route,
            source_text=document_text,
            statistics=statistics,
            calculated_results=calculated_results,
            retrieved_chunks=retrieved_chunks,
            total_pages=pages,
        )

        execution_trace.append({
            "stage": "VERIFICATION",
            "status": "completed" if verification_result["grounding_status"] != "UNGROUNDED" else "warning",
            "details": {
                "verifier": "VAULTA_VERIFIER",
                "grounding_status": verification_result["grounding_status"],
                "numeric_check": verification_result["numeric_check"],
                "source_check": verification_result["source_check"],
                "warnings": verification_result["warnings"],
                "summary": verification_result["summary"],
                "status": "completed",
            },
        })

        # OUTPUT_READY
        execution_trace.append({
            "stage": "OUTPUT_READY",
            "status": "completed",
            "details": {
                "status": "completed",
                "local": True,
                "external_calls": 0,
            },
        })

    except Exception as e:
        execution_trace.append({
            "stage": "ERROR",
            "status": "failed",
            "details": {
                "error": str(e),
            },
        })
        response_text = f"An error occurred during agent execution: {e}"
        verification_result = {
            "grounding_status": "UNGROUNDED",
            "numeric_check": "N/A",
            "source_check": "ERROR",
            "warnings": [str(e)],
            "summary": "Execution encountered an error.",
        }

    return {
        "route": route,
        "confidence": confidence,
        "reason": reason,
        "response": response_text,
        "model": MODEL,
        "local": True,
        "external_calls": 0,
        "pages": pages,
        "text": document_text,
        "rows": rows,
        "columns": columns,
        "numeric_columns": numeric_columns,
        "statistics": statistics,
        "calculated_results": calculated_results,
        "retrieved_chunks": retrieved_chunks,
        "verification": verification_result,
        "execution_trace": execution_trace,
    }