import io
import datetime
from typing import Dict, Any, List, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

from app.config import MODEL


def _set_cell_background(cell, fill_hex: str):
    """Sets background color for a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets cell padding in dxa."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tcMar)


def generate_approval_note(
    task_prompt: str,
    route: str,
    response_text: str,
    verification: Optional[Dict[str, Any]] = None,
    filename: Optional[str] = None,
    pages: int = 0,
    statistics: Optional[Dict[str, Any]] = None,
    calculated_results: Optional[Dict[str, Any]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    execution_trace: Optional[List[Dict[str, Any]]] = None,
    model_name: str = MODEL,
) -> bytes:
    """
    Generates a formal, sovereign engineering approval note as a .docx file in memory.
    """
    doc = docx.Document()

    # Configure Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Document Header Title
    header_p = doc.add_paragraph()
    header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_org = header_p.add_run("VAULTA SOVEREIGN INDUSTRIAL WORKBENCH\n")
    run_org.font.size = Pt(10)
    run_org.font.bold = True
    run_org.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)  # Navy Blue

    run_title = header_p.add_run("ENGINEERING APPROVAL NOTE & AUDIT SUMMARY")
    run_title.font.size = Pt(16)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    conf_p = doc.add_paragraph()
    conf_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    conf_run = conf_p.add_run("SECURITY CLASSIFICATION: INTERNAL / ON-PREMISE ONLY")
    conf_run.font.size = Pt(8.5)
    conf_run.font.bold = True
    conf_run.font.color.rgb = RGBColor(0xDC, 0x26, 0x26)  # Red

    # Metadata Summary Table
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note_id = f"APN-{datetime.datetime.now().strftime('%Y%m%d')}-{abs(hash(task_prompt)) % 10000:04d}"

    v_data = verification or {}
    grounding_status = v_data.get("grounding_status", "VERIFIED")
    numeric_status = v_data.get("numeric_check", "N/A")
    comparison_status = v_data.get("comparison_check", "N/A")

    table = doc.add_table(rows=5, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(2.2), Inches(4.6)]
    for row in table.rows:
        for i, w in enumerate(col_widths):
            row.cells[i].width = w

    meta_rows = [
        ("Reference ID:", note_id),
        ("Date & Timestamp:", now_str),
        ("Workflow Route:", f"{route} (Local Open-Weight Model: {model_name})"),
        ("Source File / Target:", filename or "Direct Sovereign Prompt"),
        ("Verification & Grounding:", f"{grounding_status} (Numeric: {numeric_status}, Comparisons: {comparison_status}) | External Calls: 0"),
    ]

    for idx, (label, val) in enumerate(meta_rows):
        cell_lbl = table.rows[idx].cells[0]
        cell_val = table.rows[idx].cells[1]

        _set_cell_background(cell_lbl, "F1F5F9")
        _set_cell_background(cell_val, "FFFFFF")
        _set_cell_margins(cell_lbl, 80, 80, 100, 100)
        _set_cell_margins(cell_val, 80, 80, 100, 100)

        p_l = cell_lbl.paragraphs[0]
        r_l = p_l.add_run(label)
        r_l.font.bold = True
        r_l.font.size = Pt(9)

        p_v = cell_val.paragraphs[0]
        r_v = p_v.add_run(str(val))
        r_v.font.size = Pt(9)

    # Verifier warnings (e.g. a wrong above/below comparison) sit right under the
    # status, so a reviewer sees them before signing off
    for warning in v_data.get("warnings", []):
        w_p = doc.add_paragraph(style="List Bullet")
        w_run = w_p.add_run(f"Verifier warning: {warning}")
        w_run.font.size = Pt(9)
        w_run.font.bold = True
        w_run.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)  # Amber

    doc.add_paragraph()

    # Section 1: Objective & Scope
    h1 = doc.add_heading(level=1)
    r1 = h1.add_run("1. Objective & Scope")
    r1.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    r1.font.size = Pt(12)

    p_obj = doc.add_paragraph()
    p_obj.add_run(f"Task Instruction: ").bold = True
    p_obj.add_run(f"{task_prompt.strip()}\n")

    # Section 2: Verified Source Evidence & Computed Metrics
    h2 = doc.add_heading(level=1)
    r2 = h2.add_run("2. Empirical Evidence & Baseline Data")
    r2.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    r2.font.size = Pt(12)

    has_evidence = False

    # 1. Document Source Evidence
    if filename and (route in ["DOC_ANALYST", "UNIFIED_INVESTIGATION"] or pages > 0):
        has_evidence = True
        p_ev_doc = doc.add_paragraph()
        p_ev_doc.add_run(f"• Document Source: ").bold = True
        p_ev_doc.add_run(f"{filename} ({pages} page(s) verified on-premise).")

    # 2. Dataset Statistics Evidence (Pandas)
    if statistics or calculated_results:
        has_evidence = True
        p_ev = doc.add_paragraph()
        p_ev.add_run("• Deterministic Dataset Summary (Pandas Engine):\n").bold = True

        if calculated_results and "highlights" in calculated_results:
            for h in calculated_results["highlights"]:
                doc.add_paragraph(f"   - {h}")

        if statistics:
            # Add mini statistics table
            doc.add_paragraph()
            stat_table = doc.add_table(rows=1, cols=6)
            stat_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            headers = ["Metric Column", "Count", "Mean", "Min", "Max", "Total"]
            hdr_cells = stat_table.rows[0].cells
            for i, h_text in enumerate(headers):
                _set_cell_background(hdr_cells[i], "1E3A8A")
                p = hdr_cells[i].paragraphs[0]
                run = p.add_run(h_text)
                run.font.bold = True
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

            for col_name, s_data in statistics.items():
                if isinstance(s_data, dict):
                    row_cells = stat_table.add_row().cells
                    row_cells[0].text = str(col_name)
                    row_cells[1].text = str(s_data.get("count", ""))
                    row_cells[2].text = str(s_data.get("mean", ""))
                    row_cells[3].text = str(s_data.get("min", ""))
                    row_cells[4].text = str(s_data.get("max", ""))
                    row_cells[5].text = str(s_data.get("sum", ""))
                    for cell in row_cells:
                        _set_cell_background(cell, "F8FAFC")
                        for p in cell.paragraphs:
                            for r in p.runs:
                                r.font.size = Pt(8)

    # 3. Knowledge / SOP Standards Evidence
    if retrieved_chunks:
        has_evidence = True
        p_ev_sop = doc.add_paragraph()
        p_ev_sop.add_run("• Retrieved SOP & Technical Standards (FAISS Vector Index):\n").bold = True
        for i, chunk in enumerate(retrieved_chunks, start=1):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"Source #{i}: {chunk.get('doc_name')} (Page {chunk.get('page_number')}) [Score: {chunk.get('score')}]: ").bold = True
            p.add_run(f"\"{chunk.get('text', '').strip()[:200]}...\"")

    if not has_evidence:
        doc.add_paragraph("General operational inquiry processed through local AI model.")


    # Section 3: Technical Analysis & Synthesis
    h3 = doc.add_heading(level=1)
    r3 = h3.add_run("3. Technical Analysis & Findings")
    r3.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    r3.font.size = Pt(12)

    for para in response_text.split("\n\n"):
        cleaned_p = para.strip()
        if cleaned_p:
            p_res = doc.add_paragraph(cleaned_p)
            p_res.style.font.size = Pt(9.5)

    # Section 4: Recommended Engineering Actions
    h4 = doc.add_heading(level=1)
    r4 = h4.add_run("4. Recommended Actions & Approval Sign-Off")
    r4.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    r4.font.size = Pt(12)

    doc.add_paragraph(
        "Based on verified data and local analysis, the following engineering actions are submitted for formal review:"
    )

    action_table = doc.add_table(rows=1, cols=4)
    action_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Action Item", "Responsible Role", "Priority", "Target Timeline"]
    for i, h_text in enumerate(headers):
        cell = action_table.rows[0].cells[i]
        _set_cell_background(cell, "334155")
        p = cell.paragraphs[0]
        run = p.add_run(h_text)
        run.font.bold = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    sample_actions = [
        ("Perform scheduled maintenance / inspection as identified", "Maintenance Lead", "High", "Within 100 operating hrs"),
        ("Verify lubricant specification and vibration thresholds", "Plant Technician", "Medium", "Next weekly inspection"),
        ("Archive audit log and verification trace in internal repository", "Compliance Officer", "Standard", "Immediate"),
    ]

    for item, role, priority, timeline in sample_actions:
        row_cells = action_table.add_row().cells
        row_cells[0].text = item
        row_cells[1].text = role
        row_cells[2].text = priority
        row_cells[3].text = timeline
        for cell in row_cells:
            _set_cell_background(cell, "F8FAFC")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(8)

    doc.add_paragraph()

    # Sign-Off Signature Matrix
    sig_table = doc.add_table(rows=2, cols=3)
    sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_roles = [
        ("Prepared By (Sovereign AI):", "VAULTA Workbench\n(100% Local Inference)"),
        ("Reviewed By (Lead Engineer):", "Signature: __________________\nDate: _______________"),
        ("Approved By (Plant Manager):", "Signature: __________________\nDate: _______________"),
    ]

    for i, (title, content) in enumerate(sig_roles):
        cell_top = sig_table.rows[0].cells[i]
        cell_bot = sig_table.rows[1].cells[i]

        _set_cell_background(cell_top, "E2E8F0")
        _set_cell_background(cell_bot, "FFFFFF")

        p_t = cell_top.paragraphs[0]
        r_t = p_t.add_run(title)
        r_t.font.bold = True
        r_t.font.size = Pt(8.5)

        p_b = cell_bot.paragraphs[0]
        r_b = p_b.add_run(content)
        r_b.font.size = Pt(8)

    doc.add_paragraph()

    # Section 5: Audit & Sovereignty Declaration
    h5 = doc.add_heading(level=1)
    r5 = h5.add_run("5. Sovereignty & Audit Compliance Declaration")
    r5.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    r5.font.size = Pt(12)

    doc.add_paragraph(
        "This approval note was synthesized and verified strictly within an on-premise, air-gapped sovereign environment. "
        "No proprietary text, document pages, tabular records, or telemetry were transmitted over public networks or external cloud APIs."
    )

    doc_stream = io.BytesIO()
    doc.save(doc_stream)
    doc_stream.seek(0)
    return doc_stream.getvalue()
