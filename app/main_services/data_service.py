import io
import json
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from app.main_services.ollama_service import ask_local_ai, MODEL


def load_dataset(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Safely loads a CSV or Excel dataset into a Pandas DataFrame in-memory.
    """
    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    lower_name = filename.lower()
    
    if lower_name.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {e}")

    elif lower_name.endswith((".xlsx", ".xlsm")):
        try:
            return pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        except Exception as e:
            raise ValueError(f"Failed to parse Excel (.xlsx) file: {e}")

    elif lower_name.endswith(".xls"):
        try:
            return pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Excel .xls format requires an additional engine (such as xlrd). Please convert to .xlsx or .csv: {e}")

    else:
        raise ValueError(f"Unsupported file format '{filename}'. Supported formats: .csv, .xlsx")


def compute_deterministic_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Performs purely deterministic Pandas calculations on the DataFrame.
    """
    rows = int(len(df))
    columns = [str(col) for col in df.columns]
    missing_values = {str(col): int(cnt) for col, cnt in df.isnull().sum().items()}

    numeric_df = df.select_dtypes(include=[np.number])
    numeric_columns = [str(col) for col in numeric_df.columns]

    # Identify primary identifier/entity column (e.g. equipment, name, id, machine)
    non_numeric_cols = [c for c in columns if c not in numeric_columns]
    id_col = None
    if non_numeric_cols:
        # Look for typical identifier keywords
        for candidate in non_numeric_cols:
            low = candidate.lower()
            if any(k in low for k in ["equipment", "machine", "asset", "id", "name", "device", "unit", "item", "tag"]):
                id_col = candidate
                break
        if not id_col:
            id_col = non_numeric_cols[0]

    statistics: Dict[str, Dict[str, Any]] = {}
    extremes: Dict[str, Dict[str, Any]] = {}
    highlights: List[str] = []

    if rows == 0:
        return {
            "rows": 0,
            "columns": columns,
            "numeric_columns": numeric_columns,
            "missing_values": missing_values,
            "statistics": {},
            "calculated_results": {
                "summary": {},
                "extremes": {},
                "highlights": ["The dataset contains 0 rows."],
            },
        }

    for col in numeric_columns:
        s = numeric_df[col].dropna()
        if len(s) == 0:
            continue

        mean_val = round(float(s.mean()), 2)
        median_val = round(float(s.median()), 2)
        min_val = round(float(s.min()), 2)
        max_val = round(float(s.max()), 2)
        sum_val = round(float(s.sum()), 2)
        std_val = round(float(s.std()), 2) if len(s) > 1 else 0.0
        count_val = int(len(s))

        statistics[col] = {
            "count": count_val,
            "mean": mean_val,
            "median": median_val,
            "min": min_val,
            "max": max_val,
            "sum": sum_val,
            "std": std_val,
        }

        # Extremes
        max_idx = s.idxmax()
        min_idx = s.idxmin()

        max_entity = str(df.loc[max_idx, id_col]) if id_col and id_col in df.columns else f"Row {max_idx}"
        min_entity = str(df.loc[min_idx, id_col]) if id_col and id_col in df.columns else f"Row {min_idx}"

        extremes[col] = {
            "max": {
                "value": max_val,
                "entity": max_entity,
                "entity_column": id_col,
                "index": int(max_idx),
            },
            "min": {
                "value": min_val,
                "entity": min_entity,
                "entity_column": id_col,
                "index": int(min_idx),
            },
        }

        # Generate clear readable highlights
        if id_col and id_col in df.columns:
            highlights.append(f"Average {col}: {mean_val}")
            highlights.append(f"Highest {col}: {max_val} ({id_col}: {max_entity})")
            highlights.append(f"Lowest {col}: {min_val} ({id_col}: {min_entity})")
            highlights.append(f"Total {col}: {sum_val}")
        else:
            highlights.append(f"Average {col}: {mean_val}")
            highlights.append(f"Highest {col}: {max_val} (Row {max_idx})")
            highlights.append(f"Lowest {col}: {min_val} (Row {min_idx})")
            highlights.append(f"Total {col}: {sum_val}")

    if not numeric_columns:
        highlights.append("No numeric columns found in dataset for calculations.")

    calculated_results = {
        "summary": statistics,
        "extremes": extremes,
        "highlights": highlights,
    }

    return {
        "rows": rows,
        "columns": columns,
        "numeric_columns": numeric_columns,
        "missing_values": missing_values,
        "statistics": statistics,
        "calculated_results": calculated_results,
    }


def build_data_interpretation_prompt(
    question: str,
    filename: str,
    rows: int,
    columns: List[str],
    numeric_columns: List[str],
    statistics: Dict[str, Any],
    highlights: List[str],
) -> str:
    stats_json = json.dumps(statistics, indent=2)
    highlights_str = "\n".join(f"- {h}" for h in highlights)

    return f"""You are VAULTA, a sovereign industrial data analyst.
Analyze and explain the deterministic calculations computed from the dataset '{filename}' to answer the user's question.

CRITICAL RULES:
- Base your response strictly and exclusively on the pre-computed deterministic results provided below.
- Do NOT recalculate, guess, or modify the numbers.
- State the exact computed values (averages, maximums, minimums, equipment names) clearly.
- Keep the response professional, concise, and structured.

USER QUESTION:
{question}

DATASET OVERVIEW:
- File: {filename}
- Total Rows: {rows}
- Columns: {", ".join(columns)}
- Numeric Columns: {", ".join(numeric_columns) if numeric_columns else "None"}

PRE-COMPUTED DETERMINISTIC RESULTS:
{highlights_str}

DESCRIPTIVE STATISTICS:
{stats_json}

Provide your concise interpretation and answer:"""


def analyze_dataset(
    file_bytes: bytes,
    filename: str,
    question: str = "Analyze this dataset and summarize key metrics.",
) -> Dict[str, Any]:
    """
    Coordinates local Pandas calculation and local Ollama interpretation.
    """
    df = load_dataset(file_bytes, filename)
    analysis = compute_deterministic_analysis(df)

    prompt = build_data_interpretation_prompt(
        question=question,
        filename=filename,
        rows=analysis["rows"],
        columns=analysis["columns"],
        numeric_columns=analysis["numeric_columns"],
        statistics=analysis["statistics"],
        highlights=analysis["calculated_results"]["highlights"],
    )

    interpretation = ask_local_ai(prompt)

    return {
        "filename": filename,
        "rows": analysis["rows"],
        "columns": analysis["columns"],
        "numeric_columns": analysis["numeric_columns"],
        "missing_values": analysis["missing_values"],
        "statistics": analysis["statistics"],
        "calculated_results": analysis["calculated_results"],
        "interpretation": interpretation,
        "model": MODEL,
        "local": True,
        "external_calls": 0,
    }
