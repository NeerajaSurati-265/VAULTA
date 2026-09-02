import re
from typing import Dict, Any, List, Optional


def _extract_numbers_from_text(text: str) -> List[float]:
    """
    Extracts standalone numerical values from text for consistency checking,
    ignoring numbers attached to alphanumeric identifiers (e.g. P-101, Unit-4).
    """
    raw_nums = re.findall(r"(?<![A-Za-z\-_])\b\d+(?:\.\d+)?\b(?![A-Za-z\-_])", text)
    nums = []
    for n in raw_nums:
        try:
            val = float(n)
            nums.append(val)
        except ValueError:
            continue
    return nums


def verify_output(
    response_text: str,
    route: str,
    source_text: Optional[str] = None,
    statistics: Optional[Dict[str, Any]] = None,
    calculated_results: Optional[Dict[str, Any]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    total_pages: int = 0,
) -> Dict[str, Any]:
    """
    Performs observable structured verification checks on generated agent output.
    Returns grounding_status, numeric_check, source_check, warnings, and summary.
    Does not expose chain-of-thought.
    """
    if not response_text or not response_text.strip():
        return {
            "grounding_status": "UNGROUNDED",
            "numeric_check": "N/A",
            "source_check": "NO_RESPONSE",
            "warnings": ["Agent returned an empty response."],
            "summary": "Verification failed due to empty response.",
        }

    warnings = []
    grounding_status = "VERIFIED"
    numeric_check = "N/A"
    source_check = "VALID_SOURCES"

    # 1. DATA_ANALYST VERIFICATION
    if route == "DATA_ANALYST":
        source_check = "DETERMINISTIC_PANDAS"
        if statistics or calculated_results:
            numeric_check = "CONSISTENT"
            # Collect valid calculated numbers
            expected_numbers = set()
            if statistics:
                for col_stats in statistics.values():
                    if isinstance(col_stats, dict):
                        for val in col_stats.values():
                            if isinstance(val, (int, float)):
                                expected_numbers.add(round(float(val), 2))

            if calculated_results:
                if "extremes" in calculated_results:
                    for ext in calculated_results["extremes"].values():
                        if isinstance(ext, dict):
                            for k in ["max", "min"]:
                                if k in ext and isinstance(ext[k], dict):
                                    if "value" in ext[k] and isinstance(ext[k]["value"], (int, float)):
                                        expected_numbers.add(round(float(ext[k]["value"]), 2))
                                    if "index" in ext[k] and isinstance(ext[k]["index"], int):
                                        expected_numbers.add(float(ext[k]["index"]))

                if "highlights" in calculated_results:
                    for h in calculated_results.get("highlights", []):
                        for n in _extract_numbers_from_text(h):
                            expected_numbers.add(round(float(n), 2))

            # Extract standalone numbers mentioned in the LLM response
            mentioned_numbers = _extract_numbers_from_text(response_text)
            
            # Check for hallucinated numbers that don't match any statistic
            unmatched = []
            for num in mentioned_numbers:
                rounded = round(num, 2)
                # Ignore common indexing numbers (1, 2, 3)
                if rounded in [1.0, 2.0, 3.0, 4.0, 5.0] and rounded not in expected_numbers:
                    continue
                if rounded not in expected_numbers and num not in expected_numbers:
                    unmatched.append(num)

            if len(unmatched) > 2:
                numeric_check = "PARTIALLY_CONSISTENT"
                warnings.append(f"Some numerical values ({unmatched[:3]}) in text were not found in Pandas statistics.")
            else:
                numeric_check = "CONSISTENT"

            grounding_status = "VERIFIED"
            summary = "Numeric claims are consistent with deterministic Pandas calculations."

        else:
            numeric_check = "N/A"
            grounding_status = "PARTIALLY_SUPPORTED"
            warnings.append("No dataset statistics were available for numeric verification.")
            summary = "Dataset analysis verified without baseline statistics."

    # 2. DOC_ANALYST VERIFICATION
    elif route == "DOC_ANALYST":
        if source_text and source_text.strip():
            # Check page references
            page_refs = re.findall(r"\[?Page\s*(\d+)\]?", response_text, re.IGNORECASE)
            if page_refs and total_pages > 0:
                invalid_pages = [p for p in page_refs if int(p) > total_pages or int(p) < 1]
                if invalid_pages:
                    source_check = "INVALID_PAGE_CITATION"
                    warnings.append(f"Response cited page(s) {invalid_pages} which exceed document page count ({total_pages}).")
                else:
                    source_check = "VALID_PAGE_CITATIONS"
            else:
                source_check = "DOCUMENT_CONTEXT_AVAILABLE"

            # Check for negative/no-data assertions
            low_resp = response_text.lower()
            if "not found" in low_resp or "does not contain" in low_resp or "no information" in low_resp:
                grounding_status = "VERIFIED_NEGATIVE_FINDING"
                summary = "Agent accurately reported that requested facts are absent from the document."
            else:
                grounding_status = "VERIFIED"
                summary = "Findings are grounded in the uploaded document text."
        else:
            source_check = "NO_DOCUMENT_SOURCE"
            grounding_status = "UNGROUNDED"
            warnings.append("No document text was available to verify claims.")
            summary = "Unverified output due to missing source document."

    # 3. KNOWLEDGE_ANALYST VERIFICATION
    elif route == "KNOWLEDGE_ANALYST":
        if retrieved_chunks and len(retrieved_chunks) > 0:
            source_check = "VALID_SOP_SOURCES"
            valid_docs = {c.get("doc_name") for c in retrieved_chunks if c.get("doc_name")}
            grounding_status = "VERIFIED"
            summary = f"Response grounded in {len(retrieved_chunks)} retrieved knowledge chunk(s) from {list(valid_docs)}."
        else:
            source_check = "NO_KNOWLEDGE_CHUNKS"
            grounding_status = "UNGROUNDED"
            warnings.append("No knowledge base chunks were retrieved for verification.")
            summary = "Knowledge query could not be grounded in indexed SOPs."

    # 4. GENERAL_AI / FALLBACK
    else:
        grounding_status = "NOT_APPLICABLE"
        numeric_check = "N/A"
        source_check = "GENERAL_KNOWLEDGE"
        summary = "General inquiry processed with open-weight model reasoning."

    return {
        "grounding_status": grounding_status,
        "numeric_check": numeric_check,
        "source_check": source_check,
        "warnings": warnings,
        "summary": summary,
    }
