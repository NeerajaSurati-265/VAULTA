import pandas as pd

from app.main_services.data_service import compute_deterministic_analysis
from app.main_services.verifier_service import verify_output
from tests.conftest import SPREADSHEETS


def test_made_up_numbers_are_flagged_partially_consistent():
    analysis = compute_deterministic_analysis(pd.read_csv(SPREADSHEETS / "maintenance_metrics.csv"))
    answer = "Average downtime was 47.31 hours, peak 88.17, lowest 0.73 and total 999.91 hours."

    result = verify_output(
        response_text=answer,
        route="DATA_ANALYST",
        statistics=analysis["statistics"],
        calculated_results=analysis["calculated_results"],
    )
    assert result["numeric_check"] == "PARTIALLY_CONSISTENT"


def test_citing_a_page_beyond_the_document_is_invalid():
    result = verify_output(
        response_text="The vibration limit is stated on Page 7.",
        route="DOC_ANALYST",
        source_text="[Page 1]\nVibration limit 4.5 mm/s",
        total_pages=2,
    )
    assert result["source_check"] == "INVALID_PAGE_CITATION"


def _kb_verify(answer):
    return verify_output(
        response_text=answer,
        route="KNOWLEDGE_ANALYST",
        retrieved_chunks=[{"doc_name": "SOP-PUMP-402.pdf", "page_number": 2, "text": "warning 4.5 mm/s"}],
    )


def test_wrong_exceeding_claim_is_a_contradiction():
    # The live Pump-402 answer of 2026-10-27 (E4)
    result = _kb_verify(
        "The peak vibration velocity was recorded at 3.8 mm/s RMS, "
        "exceeding the warning threshold of 4.5 mm/s RMS."
    )
    assert result["comparison_check"] == "CONTRADICTION"
    assert result["grounding_status"] == "PARTIALLY_SUPPORTED"
    assert any("3.8" in w and "4.5" in w for w in result["warnings"])


def test_wrong_above_claim_across_unit_spellings():
    result = _kb_verify("Bearing temperature of 68 degC is slightly above the recommended 75 °C.")
    assert result["comparison_check"] == "CONTRADICTION"


def test_wrong_just_at_claim_with_unitless_threshold():
    result = _kb_verify("Vibration of 3.8 mm/s is just at the 4.5 threshold.")
    assert result["comparison_check"] == "CONTRADICTION"


def test_correct_comparisons_are_consistent():
    for answer in (
        "5.2 mm/s exceeds the 4.5 mm/s limit.",
        "3.8 mm/s does not exceed 4.5 mm/s.",
        "The limit of 4.5 mm/s was exceeded by the reading of 5.2 mm/s.",
    ):
        result = _kb_verify(answer)
        assert result["comparison_check"] == "CONSISTENT", answer
        assert result["grounding_status"] == "VERIFIED", answer


def test_no_comparison_and_identifiers_are_ignored():
    # "at" is not a comparison, P-402 is an ID, and h vs mm/s do not compare
    result = _kb_verify("Pump P-402 ran 12 h at 3.8 mm/s; inspect within 100 operating hours.")
    assert result["comparison_check"] == "N/A"
    assert result["comparison_issues"] == []


def test_general_ai_answer_stays_not_applicable_but_warns():
    result = verify_output(response_text="3.8 mm/s is above 4.5 mm/s.", route="GENERAL_AI")
    assert result["grounding_status"] == "NOT_APPLICABLE"
    assert result["comparison_check"] == "CONTRADICTION"
    assert result["warnings"]


SOP_LIMITS = "- Warning vibration threshold: 4.5 mm/s RMS.\n- Discharge temperature alarm: 105 degC. Automatic trip: 110 degC."


def test_claim_against_a_named_limit_from_the_sources():
    # Live answer of 2026-10-27: the 4.5 is only in the SOP, not in the sentence
    result = verify_output(
        response_text="The current vibration level of 3.8 mm/s (RMS) is at the warning threshold.",
        route="DOC_ANALYST",
        source_text=SOP_LIMITS,
    )
    assert result["comparison_check"] == "CONTRADICTION"
    assert result["grounding_status"] == "PARTIALLY_SUPPORTED"


def test_named_limit_claims_that_hold_and_ambiguous_ones():
    ok = verify_output(
        response_text="Discharge temperature of 108 degC is above the alarm limit but below the trip limit.",
        route="DOC_ANALYST",
        source_text=SOP_LIMITS,
    )
    assert ok["comparison_check"] == "CONSISTENT"

    # "this threshold" with two degC limits (alarm 105, trip 110): not checked
    ambiguous = verify_output(
        response_text="Discharge temperature of 108 degC is above this threshold.",
        route="DOC_ANALYST",
        source_text=SOP_LIMITS,
    )
    assert ambiguous["comparison_check"] == "N/A"
