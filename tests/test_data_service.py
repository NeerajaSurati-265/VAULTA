import csv

import pandas as pd

from app.main_services.data_service import compute_deterministic_analysis
from tests.conftest import SPREADSHEETS

CSV_PATH = SPREADSHEETS / "maintenance_metrics.csv"


def _expected_from_csv():
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    def is_number(v):
        try:
            float(v)
            return True
        except ValueError:
            return False

    numeric = [col for col in rows[0] if all(is_number(r[col]) for r in rows)]
    return rows, numeric


def test_row_count_and_numeric_columns_match_the_csv():
    rows, numeric = _expected_from_csv()
    analysis = compute_deterministic_analysis(pd.read_csv(CSV_PATH))

    assert analysis["rows"] == len(rows)
    assert analysis["numeric_columns"] == numeric
    for col in numeric:
        values = [float(r[col]) for r in rows]
        assert analysis["statistics"][col]["max"] == round(max(values), 2)
        assert analysis["statistics"][col]["sum"] == round(sum(values), 2)
