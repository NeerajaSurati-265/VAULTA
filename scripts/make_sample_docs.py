"""
Generates the synthetic sample documents in data/documents/.

These PDFs are fictional (equipment IDs, limits and readings are made up) and
exist so the knowledge base and the retrieval eval (eval/questions.jsonl) have
a realistic multi-document corpus. Page 1 of each is labelled
"Synthetic sample document".

SOP-PUMP-402.pdf was originally hand-made and its long trip-limit line ran off
the right edge of page 2, so text extraction cut it off (U7). It is generated
here with the same wording; insert_textbox wraps lines and refuses text that
does not fit, so no document can be silently truncated.

Usage (from the repo root):
    python scripts/make_sample_docs.py
"""
from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
LABEL = "Synthetic sample document - fictional data for demos and evaluation only."
# Fixed metadata so re-running the script produces identical files
FIXED_DATE = "D:20260901000000Z"

DOCUMENTS = {
    "SOP-PUMP-402.pdf": [
        """STANDARD OPERATING PROCEDURE: PUMP-402
Document ID: SOP-PUMP-402-REV3
Equipment: Industrial Centrifugal Feed Pump

1. Lubrication Protocol:
- Grease levels must be inspected every 120 operating hours.
- Use only synthetic ISO VG 68 lubricant for bearing housings.
- Avoid overfilling lubricant reservoir above the max sight-glass level.""",
        """2. Vibration and Temperature Thresholds:
- Normal operating vibration: < 3.5 mm/s RMS.
- Warning vibration threshold: 4.5 mm/s RMS.
- Maximum allowable RMS vibration before trip is 4.5 mm/s. If vibration exceeds 5.0 mm/s, immediately trip the emergency stop circuit.
- Drive end bearing temperature must not exceed 75°C under continuous load.""",
    ],
    "SOP-COMP-210.pdf": [
        """STANDARD OPERATING PROCEDURE: COMPRESSOR C-210
Document ID: SOP-COMP-210-REV2
Equipment: Rotary Screw Air Compressor C-210, Unit 4 Utilities

1. Start-Up Procedure:
- Verify the oil level in the separator sight glass is between the MIN and MAX marks.
- Open discharge isolation valve V-211 fully before starting.
- Start the compressor in unloaded mode and wait 30 seconds before loading.
- Confirm discharge pressure reaches 7.5 bar(g) within 2 minutes of loading.
- If pressure is not reached, unload, stop the machine and check for air leaks.""",
        """2. Operating Limits:
- Normal discharge temperature: 80 to 95 degC.
- Discharge temperature alarm: 105 degC. Automatic trip: 110 degC.
- Minimum oil pressure while loaded: 2.0 bar.
- Airend housing vibration must stay below 7.1 mm/s RMS (ISO 10816 zone B).
- Inlet air filter: replace the filter element when differential pressure exceeds 50 mbar.
- Never operate with the enclosure doors open; cooling airflow depends on them.""",
        """3. Maintenance Intervals:
- Change compressor oil (synthetic PAO, ISO VG 46) every 4,000 running hours.
- Replace the oil filter and the separator element every 4,000 running hours.
- Drain condensate traps daily and confirm the automatic drain valve cycles.
- Inspect drive belt tension every 500 running hours; adjust if deflection exceeds 10 mm.
- Record all readings on log sheet CL-210 and report deviations to the shift supervisor.""",
    ],
    "MAN-BRG-115.pdf": [
        """BEARING MAINTENANCE MANUAL
Document ID: MAN-BRG-115
Scope: Deep groove ball bearings and spherical roller bearings on pumps, fans and motors.

1. Installation:
- Heat the bearing with an induction heater to a maximum of 110 degC.
- Never use an open flame to heat a bearing; it destroys the heat treatment.
- Mount the bearing with a fitting sleeve that presses only on the ring being fitted.
- Check radial internal clearance with a feeler gauge after mounting.
- Record the bearing serial number in the asset register.""",
        """2. Lubrication:
- Use lithium complex grease, consistency NLGI 2, unless the equipment datasheet says otherwise.
- Relubrication quantity in grams: G = 0.005 x D x B (D = outside diameter, B = width, in mm).
- Over-greasing causes churning and a temperature rise of 10 to 15 degC; stop adding grease
  when fresh grease appears at the relief port.
- Never mix greases with different thickener types.
- Shielded (2Z) bearings are lubricated for life and must not be regreased.""",
        """3. Failure Diagnosis:
- Spalling (flaking) on the raceway indicates rolling contact fatigue at end of life.
- Brinelling (indentations in the raceway) indicates impact or static overload, often during transport.
- Fluting (washboard pattern) is caused by electrical current passing through the bearing;
  install an insulated bearing or a shaft grounding brush.
- Blue or brown discoloration indicates overheating from lubricant starvation.
- Envelope acceleration above 4 gE requires inspection within one week.""",
    ],
    "SOP-LOTO-001.pdf": [
        """LOCKOUT/TAGOUT (LOTO) PROCEDURE
Document ID: SOP-LOTO-001
Purpose: Control hazardous energy while equipment is serviced or maintained.

1. Preparation:
- Notify all affected employees that the equipment will be locked out and why.
- Identify every energy source (electrical, pneumatic, hydraulic, stored mechanical, thermal)
  using the equipment energy isolation list.
- Collect a personal padlock and a danger tag from the LOTO station.
- Each padlock has a single key, kept by the person who applies it.""",
        """2. Isolation Steps:
- Shut down the equipment with its normal stop control.
- Isolate each energy source at its isolation point: open the MCC breaker, close and chain valves.
- Apply your personal padlock and danger tag to every isolation device.
- Release stored energy: bleed pneumatic lines, block or lower suspended loads, discharge capacitors.
- Verify zero energy: press the local start button (try-step) and test conductors with a voltage tester.""",
        """3. Group Lockout and Lock Removal:
- Use a group lockout box when more than three workers service the same equipment;
  every worker attaches their own lock to the box.
- A lock may only be removed by the person who applied it.
- If that person has left site, the supervisor follows the abandoned lock procedure,
  which requires Plant Manager approval.
- Before re-energizing, account for all workers and notify affected employees.
- This procedure is audited annually.""",
    ],
    "RPT-MTR-330.pdf": [
        """MOTOR INSPECTION REPORT
Document ID: RPT-MTR-330
Equipment: Motor M-330, 110 kW induction motor driving cooling tower fan F-330
Inspection Date: 2026-09-12. Inspector: Electrical Team B

1. Electrical Tests:
- Insulation resistance: 850 MOhm at 1000 V DC (minimum acceptable 100 MOhm).
- Polarization index: 3.2.
- Winding resistance phase imbalance: 0.8 percent.
- Running current: 182 A against a nameplate rating of 195 A.""",
        """2. Mechanical and Thermal Checks:
- Non-drive end (NDE) bearing temperature: 82 degC (alarm at 90 degC).
- Drive end (DE) bearing temperature: 71 degC.
- Overall vibration: 2.9 mm/s RMS.
- Thermography: hot spot of 64 degC on the terminal box connection of phase L2;
  a loose cable lug is suspected.
- Cooling fan cowl partially blocked with dust.""",
        """3. Findings and Recommended Actions:
- Re-torque the phase L2 terminal lug at the next planned shutdown.
- Clean the fan cowl and the cooling fins.
- Regrease the NDE bearing with 15 g of grease.
- Repeat thermography within 30 days.
- Overall condition rating: B (acceptable with minor defects). The motor is fit for continued service.""",
    ],
    "SOP-HX-505.pdf": [
        """STANDARD OPERATING PROCEDURE: HEAT EXCHANGER E-505 CLEANING
Document ID: SOP-HX-505
Equipment: Shell-and-tube cooling water heat exchanger E-505

1. Performance Monitoring:
- Record inlet and outlet temperatures on both sides weekly.
- Schedule cleaning when the overall heat transfer coefficient falls 25 percent below its clean value,
  or when tube-side pressure drop exceeds 1.8 bar.
- Trend the results so fouling is caught before production is affected.""",
        """2. Cleaning Method:
- Isolate and drain the exchanger following SOP-LOTO-001.
- Remove the channel head and inspect the tube sheet.
- Hydroblast the tubes at 700 bar with a rotating nozzle.
- For hard scale, circulate 5 percent citric acid at 60 degC for 4 hours, then neutralize to pH 6 to 8.
- Never use hydrochloric acid on stainless steel tubes.""",
        """3. Reassembly and Testing:
- Replace all gaskets with new spiral wound gaskets.
- Torque the channel head bolts in a cross pattern to 450 Nm.
- Hydrostatic test at 1.5 times design pressure (15 bar) for 30 minutes with no visible leaks.
- Return the exchanger to service and record the new clean-condition temperatures.""",
    ],
}


def make_pdf(path: Path, pages):
    doc = fitz.open()
    for page_number, text in enumerate(pages, start=1):
        page = doc.new_page(width=595, height=842)  # A4
        if page_number == 1:
            text = f"{LABEL}\n\n{text}"
        # insert_textbox returns a negative number if the text did not fit
        if page.insert_textbox(fitz.Rect(56, 56, 539, 786), text, fontsize=11, fontname="helv") < 0:
            raise ValueError(f"{path.name} page {page_number}: text does not fit")
    doc.set_metadata({
        "title": path.stem,
        "author": "VAULTA synthetic sample generator",
        "creationDate": FIXED_DATE,
        "modDate": FIXED_DATE,
    })
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCUMENTS.items():
        make_pdf(OUT_DIR / name, pages)
        print(f"wrote {OUT_DIR / name} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
