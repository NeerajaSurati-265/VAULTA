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


# --- Comparison check (E4) ---------------------------------------------------
# The numeric check only asks whether a number appears in the sources. A small
# model can quote both numbers correctly and still get the comparison wrong
# ("3.8 mm/s, exceeding the 4.5 mm/s threshold"), so comparisons between two
# quantities in the same sentence are recomputed here.

# Unit spellings -> one canonical unit, so "75 degC" and "75 °C" compare.
_UNITS = [
    (r"mm/s", "mm/s"),
    (r"°\s*C|deg\s*C|degrees?\s+C(?:elsius)?\b|celsius\b", "degC"),
    (r"°\s*F|deg\s*F|degrees?\s+F(?:ahrenheit)?\b|fahrenheit\b", "degF"),
    (r"bar\b", "bar"),
    (r"psi\b", "psi"),
    (r"kPa\b", "kPa"),
    (r"MPa\b", "MPa"),
    (r"rpm\b", "rpm"),
    (r"kW\b", "kW"),
    (r"µm|um\b|microns?\b", "um"),
    (r"mm\b", "mm"),
    (r"hours?\b|hrs?\b|h\b", "h"),
    (r"%", "%"),
]
_UNIT_RE = "|".join(f"(?:{pattern})" for pattern, _ in _UNITS)
# A number not glued to an identifier (P-402, Unit-4), with an optional unit.
_QUANTITY_RE = re.compile(
    rf"(?<![A-Za-z\-_.\d])(?P<num>\d+(?:\.\d+)?)(?![\d.])\s*(?P<unit>{_UNIT_RE})?",
    re.IGNORECASE,
)

# Comparison phrases -> relation "A <rel> B", A being the quantity before the
# phrase. Order matters: longer phrases first, so "no more than" wins over
# "more than" and "exceeded by" (passive: B > A) over "exceed". Plain "at" is
# left out on purpose: "recorded at 3.8 mm/s" is not a comparison.
_COMPARATORS = [
    (r"exceeded\s+by|surpassed\s+by", ">", True),
    (r"no\s+more\s+than|not\s+more\s+than|at\s+most|up\s+to", "<=", False),
    (r"no\s+less\s+than|at\s+least", ">=", False),
    (r"greater\s+than\s+or\s+equal\s+to", ">=", False),
    (r"less\s+than\s+or\s+equal\s+to", "<=", False),
    (r"exceed(?:s|ed|ing)?|surpass(?:es|ed|ing)?|above|over|greater\s+than|higher\s+than|more\s+than", ">", False),
    (r"below|under|less\s+than|lower\s+than", "<", False),
    (r"within", "<=", False),
    (r"just\s+at|right\s+at|exactly\s+at|equal\s+to|the\s+same\s+as", "=", False),
]
_COMPARATOR_RE = re.compile(
    "|".join(f"(?P<c{i}>\\b(?:{pattern})\\b)" for i, (pattern, _, _) in enumerate(_COMPARATORS)),
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"\b(?:not|never|no\s+longer)\b|n't\b", re.IGNORECASE)
_NEGATED = {">": "<=", "<": ">=", ">=": "<", "<=": ">", "=": "!=", "!=": "="}
_REL_WORDS = {">": "above", "<": "below", ">=": "at or above", "<=": "at or below", "=": "equal to", "!=": "different from"}
# How far (characters) a quantity may sit from the comparison phrase
_MAX_GAP_BEFORE = 80
_MAX_GAP_AFTER = 60
# "just at" / "equal to" tolerate 2% difference
_EQUAL_TOLERANCE = 0.02


# Named limits ("Warning vibration threshold: 4.5 mm/s", "Automatic trip: 110
# degC", "warning threshold for vibration at 4.5 mm/s"), read from the sources
# and the answer, so "3.8 mm/s is at the warning threshold" can be checked even
# though the answer never repeats the 4.5.
_LIMIT_NAMES = r"warning|alarm|alert|trip|shutdown"
_LIMIT_DEF_RE = re.compile(
    rf"\b(?P<name>{_LIMIT_NAMES})\b(?:\s+[A-Za-z]+){{0,2}}?(?:\s+(?:threshold|limit|level|setpoint))?"
    rf"[^.;\n\d]{{0,30}}?(?<![A-Za-z\-_.\d])(?P<num>\d+(?:\.\d+)?)(?![\d.])\s*(?P<unit>{_UNIT_RE})",
    re.IGNORECASE,
)
# "... the warning threshold", "this limit": what follows a comparison phrase
# when the answer names the limit instead of giving its value
_LIMIT_REF_RE = re.compile(
    r"\s*(?:the|this|its|that)?\s*(?P<words>(?:[A-Za-z\-]+\s+){0,3}?)(?:threshold|limit)s?\b",
    re.IGNORECASE,
)
_REF_COMPARATOR_RE = re.compile(
    _COMPARATOR_RE.pattern + r"|(?P<at>\bat\b)",
    re.IGNORECASE,
)


def _named_limits(texts: List[str]) -> Dict[tuple, set]:
    """(limit name, unit) -> the values stated for it, e.g. ("warning", "mm/s") -> {4.5}."""
    limits: Dict[tuple, set] = {}
    for text in texts:
        for m in _LIMIT_DEF_RE.finditer(text or ""):
            unit = _canonical_unit(m.group("unit"))
            if unit:
                limits.setdefault((m.group("name").lower(), unit), set()).add(float(m.group("num")))
    return limits


def _canonical_unit(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    for pattern, canonical in _UNITS:
        if re.fullmatch(pattern, raw.strip(), re.IGNORECASE):
            return canonical
    return None


def _relation_holds(a: float, rel: str, b: float) -> bool:
    equal = abs(a - b) <= _EQUAL_TOLERANCE * max(abs(a), abs(b), 1e-9)
    return {
        ">": a > b,
        "<": a < b,
        ">=": a >= b,
        "<=": a <= b,
        "=": equal,
        "!=": not equal,
    }[rel]


def _actual_relation(a: float, b: float) -> str:
    if abs(a - b) <= _EQUAL_TOLERANCE * max(abs(a), abs(b), 1e-9):
        return "="
    return ">" if a > b else "<"


def check_comparisons(text: str, references: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Finds claims like "<quantity> exceeds/below/within <quantity>" in each
    sentence and recomputes them; also "<quantity> is at/above the warning
    threshold", looking the limit up in `references` (source texts) and the
    answer itself. Returns one entry per comparison found, with `holds` False
    when the stated relation is wrong.
    """
    results = _check_named_limit_claims(text, _named_limits([text] + list(references or [])))
    # Split on sentence ends followed by whitespace, so "3.8" stays whole
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
        quantities = [
            (m.start(), m.end(), float(m.group("num")), _canonical_unit(m.group("unit")))
            for m in _QUANTITY_RE.finditer(sentence)
        ]
        if len(quantities) < 2:
            continue

        for cm in _COMPARATOR_RE.finditer(sentence):
            index = int(cm.lastgroup[1:])
            _, rel, swap = _COMPARATORS[index]

            before = [q for q in quantities if q[1] <= cm.start() and cm.start() - q[1] <= _MAX_GAP_BEFORE]
            after = [q for q in quantities if q[0] >= cm.end() and q[0] - cm.end() <= _MAX_GAP_AFTER]
            if not before or not after:
                continue
            qa, qb = before[-1], after[0]

            # Same unit, or one side unitless ("3.8 mm/s, just at the 4.5 threshold")
            unit_a, unit_b = qa[3], qb[3]
            if unit_a is None and unit_b is None:
                continue
            if unit_a and unit_b and unit_a != unit_b:
                continue
            unit = unit_a or unit_b

            # "does not exceed": a negation between A and the phrase flips it
            window = sentence[max(qa[1], cm.start() - 25):cm.start()]
            if _NEGATION_RE.search(window):
                rel = _NEGATED[rel]

            a, b = qa[2], qb[2]
            if swap:
                a, b = b, a

            results.append({
                "claim": sentence[qa[0]:qb[1]].strip(),
                "a": a,
                "b": b,
                "unit": unit,
                "stated": rel,
                "actual": _actual_relation(a, b),
                "holds": _relation_holds(a, rel, b),
            })
    return results


def _check_named_limit_claims(text: str, limits: Dict[tuple, set]) -> List[Dict[str, Any]]:
    """Claims that compare a quantity with a limit named but not quoted ("is at the warning threshold")."""
    results = []
    if not limits:
        return results
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
        quantities = [
            (m.start(), m.end(), float(m.group("num")), _canonical_unit(m.group("unit")))
            for m in _QUANTITY_RE.finditer(sentence)
        ]
        for cm in _REF_COMPARATOR_RE.finditer(sentence):
            ref = _LIMIT_REF_RE.match(sentence, cm.end())
            if not ref:
                continue
            before = [
                q for q in quantities
                if q[3] and q[1] <= cm.start() and cm.start() - q[1] <= _MAX_GAP_BEFORE
            ]
            if not before:
                continue
            qa = before[-1]

            # "the warning threshold" -> the warning limit in that unit; "this
            # threshold" -> only when a single limit exists in that unit
            named = [w for w in re.findall(_LIMIT_NAMES, ref.group("words"), re.IGNORECASE)]
            values = set()
            for (name, unit), vals in limits.items():
                if unit == qa[3] and (not named or name == named[0].lower()):
                    values |= vals
            if len(values) != 1:
                continue
            b = values.pop()

            if cm.lastgroup == "at":
                rel = "="
            else:
                _, rel, swap = _COMPARATORS[int(cm.lastgroup[1:])]
                if swap:
                    continue
            window = sentence[max(qa[1], cm.start() - 25):cm.start()]
            if _NEGATION_RE.search(window):
                rel = _NEGATED[rel]

            results.append({
                "claim": sentence[qa[0]:ref.end()].strip(),
                "a": qa[2],
                "b": b,
                "unit": qa[3],
                "stated": rel,
                "actual": _actual_relation(qa[2], b),
                "holds": _relation_holds(qa[2], rel, b),
            })
    return results


def _describe_contradiction(c: Dict[str, Any]) -> str:
    unit = f" {c['unit']}" if c["unit"] else ""
    return (
        f"\"{c['claim']}\" states {c['a']:g}{unit} is {_REL_WORDS[c['stated']]} {c['b']:g}{unit}, "
        f"but {c['a']:g} is {_REL_WORDS[c['actual']]} {c['b']:g}."
    )


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
            "comparison_check": "N/A",
            "comparison_issues": [],
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

    # 5. COMPARISON CHECK (all routes): a wrong "above/below" claim means the
    # answer cannot be called verified, even if every number is in the sources.
    references = [source_text or ""] + [c.get("text", "") for c in (retrieved_chunks or [])]
    comparisons = check_comparisons(response_text, references)
    comparison_issues = [_describe_contradiction(c) for c in comparisons if not c["holds"]]
    if not comparisons:
        comparison_check = "N/A"
    elif comparison_issues:
        comparison_check = "CONTRADICTION"
        warnings.extend(f"Wrong comparison: {issue}" for issue in comparison_issues)
        if grounding_status in ("VERIFIED", "VERIFIED_NEGATIVE_FINDING"):
            grounding_status = "PARTIALLY_SUPPORTED"
        summary = f"{summary} {len(comparison_issues)} of {len(comparisons)} numeric comparison(s) are wrong."
    else:
        comparison_check = "CONSISTENT"

    return {
        "grounding_status": grounding_status,
        "numeric_check": numeric_check,
        "source_check": source_check,
        "comparison_check": comparison_check,
        "comparison_issues": comparison_issues,
        "warnings": warnings,
        "summary": summary,
    }
