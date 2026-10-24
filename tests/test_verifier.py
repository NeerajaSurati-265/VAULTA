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
