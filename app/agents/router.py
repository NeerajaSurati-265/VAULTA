import json
import re
from typing import Optional, Dict, Any

from app.main_services.ollama_service import ask_local_ai


DOC_ANALYST = "DOC_ANALYST"
DATA_ANALYST = "DATA_ANALYST"
KNOWLEDGE_ANALYST = "KNOWLEDGE_ANALYST"
GENERAL_AI = "GENERAL_AI"

VALID_ROUTES = {DOC_ANALYST, DATA_ANALYST, KNOWLEDGE_ANALYST, GENERAL_AI}

DEFAULT_FALLBACK: Dict[str, Any] = {
    "route": GENERAL_AI,
    "confidence": 0.5,
    "reason": "Default fallback to GENERAL_AI.",
}


def _build_router_prompt(
    prompt: str,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
) -> str:
    attachment_info = []
    if filename:
        attachment_info.append(f"Filename: {filename}")
    if file_type:
        attachment_info.append(f"File Type: {file_type}")
    
    attachment_str = ", ".join(attachment_info) if attachment_info else "None"

    return f"""You are the VAULTA Sovereign Task Router.
Analyze the user's task and optional file attachment, then classify it into EXACTLY ONE route:

- DOC_ANALYST: Specific uploaded PDF document, maintenance report, technical specification, or uploaded document Q&A.
- DATA_ANALYST: Tabular data, CSVs, Excel/spreadsheets, numbers, metrics, statistical analysis, or dataset calculations.
- KNOWLEDGE_ANALYST: Inquiries about internal standard operating procedures (SOPs), manuals, plant standards, regulations, or knowledge retrieval across reference documents.
- GENERAL_AI: General inquiries, concept explanations, definitions, code assistance, conversations, or tasks without specific document/data attachments.

Respond ONLY with a valid JSON object in this exact schema:
{{
  "route": "DOC_ANALYST" | "DATA_ANALYST" | "KNOWLEDGE_ANALYST" | "GENERAL_AI",
  "confidence": 0.95,
  "reason": "Brief single-sentence explanation of why this route was chosen."
}}

TASK:
{prompt.strip()}

ATTACHMENT:
{attachment_str}

JSON:"""


def _parse_router_response(raw_response: str) -> Dict[str, Any]:
    """
    Safely parses the JSON output from Ollama response, handling code blocks or text wrappers.
    """
    if not raw_response or not raw_response.strip():
        raise ValueError("Empty response received from Ollama model.")

    # Try direct JSON parsing first
    cleaned = raw_response.strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting JSON object using regex
        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"No JSON object found in response: {raw_response[:100]}")

    route = str(data.get("route", "")).strip().upper()
    if route not in VALID_ROUTES:
        raise ValueError(f"Invalid route '{route}' returned by model.")

    confidence = data.get("confidence", 0.8)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.8

    reason = str(data.get("reason", "")).strip()
    if not reason:
        reason = f"Classified as {route} by local AI model."

    return {
        "route": route,
        "confidence": confidence,
        "reason": reason,
    }


class TaskRouter:
    """
    VAULTA Task Router for classifying tasks using local LLM inference.
    """

    @staticmethod
    def route(
        prompt: str,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify a task into DOC_ANALYST, DATA_ANALYST, or GENERAL_AI.
        Guaranteed to return structured dict without raising exceptions.
        """
        if not prompt or not prompt.strip():
            # If a file is present without a prompt, route based on file hints
            if filename or file_type:
                target = (filename or file_type or "").lower()
                if target.endswith((".pdf", ".doc", ".docx", ".txt", ".md")):
                    return {
                        "route": DOC_ANALYST,
                        "confidence": 0.9,
                        "reason": f"Document file attached ({filename or file_type}).",
                    }
                elif target.endswith((".csv", ".xlsx", ".xls", ".parquet", ".json")):
                    return {
                        "route": DATA_ANALYST,
                        "confidence": 0.9,
                        "reason": f"Data file attached ({filename or file_type}).",
                    }

            return {
                "route": GENERAL_AI,
                "confidence": 1.0,
                "reason": "Empty task prompt provided.",
            }

        try:
            router_prompt = _build_router_prompt(
                prompt=prompt,
                filename=filename,
                file_type=file_type,
            )
            raw_response = ask_local_ai(router_prompt)
            return _parse_router_response(raw_response)

        except Exception as e:
            # Fallback safely: if file extension clearly indicates route, apply heuristic fallback
            target = (filename or file_type or "").lower()
            if target.endswith((".pdf", ".doc", ".docx")):
                return {
                    "route": DOC_ANALYST,
                    "confidence": 0.7,
                    "reason": f"Fallback heuristic based on document file ({filename or file_type}): {e}",
                }
            elif target.endswith((".csv", ".xlsx", ".xls")):
                return {
                    "route": DATA_ANALYST,
                    "confidence": 0.7,
                    "reason": f"Fallback heuristic based on data file ({filename or file_type}): {e}",
                }

            return {
                "route": GENERAL_AI,
                "confidence": 0.5,
                "reason": f"Fallback to GENERAL_AI due to routing error: {e}",
            }


def classify_task(
    prompt: str,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for TaskRouter.route().
    """
    return TaskRouter.route(prompt=prompt, filename=filename, file_type=file_type)
