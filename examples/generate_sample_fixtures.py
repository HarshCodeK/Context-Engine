"""Build substantial, reproducible Context Studio parser fixtures.

All text and tabular examples are original benchmark material for a fictional
community-energy programme. Image fixtures are intentionally excluded: those
must come from a real, licensed source rather than synthetic artwork.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pymupdf as fitz
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches, Pt

OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

SECTIONS = [
    ("Programme overview", "Northstar Community Energy is a fictional cooperative programme designed to make rooftop solar and building efficiency accessible to small organisations. The pilot covers libraries, clinics, community halls and small manufacturers across three districts. The programme combines a transparent procurement framework, local installation partners, a shared maintenance desk and a public performance ledger. Its purpose is not to maximise installed capacity at any cost; it is to deliver dependable savings, safe installations and measurable community benefit over the full operating life of each asset."),
    ("Operating model", "Each site begins with a consent-led energy assessment. The survey records the meter arrangement, roof condition, shading, structural constraints, fire access, critical loads and the site's opening hours. A qualified engineer signs off the design before procurement. Installers submit a method statement, insurance evidence, electrical credentials, a commissioning checklist and a named escalation contact. The cooperative retains the as-built diagram, serial numbers, warranty dates and maintenance schedule. Site staff receive a plain-language handover and know how to isolate the system safely."),
    ("Data and measurement", "The measurement plan distinguishes generation, self-consumption, grid import, export, downtime and weather-normalised performance. Meter readings are timestamped in local time and retain their original unit. Missing readings are marked as missing rather than silently interpolated. The monthly report shows the reporting period, data completeness, meter source, calculation method and any corrections. Savings are estimated against a documented baseline and are never presented as guaranteed cash returns. Personal information from staff or visitors is excluded from the public dashboard."),
    ("Financial controls", "The pilot budget separates survey, design, equipment, installation, grid connection, training, monitoring and contingency. Purchase orders require an approved scope and two-person authorisation above the delegated threshold. Invoices are matched to accepted milestones and commissioning evidence. Variations require a written reason, cost impact, schedule impact and approval before work proceeds. The finance team reconciles grant receipts, cooperative contributions and supplier payments each month. Forecasts show committed cost separately from paid cost and unallocated contingency."),
    ("Safety and resilience", "The safety plan covers working at height, electrical isolation, manual handling, weather exposure, fire service access and public protection. Contractors complete a site-specific risk assessment and toolbox briefing before work. The programme pauses work when wind, rain, heat or roof conditions exceed the approved method statement. Critical facilities retain their existing emergency procedures; solar equipment is not described as backup power unless an approved storage and islanding design is installed. Incidents and near misses are logged, reviewed and assigned corrective actions."),
    ("Community participation", "Residents and site teams can review the proposed installation, ask questions and request accessible explanations before a site is approved. Engagement records distinguish attendance from consent. The cooperative publishes expected disruption, contact routes, complaint response targets and the process for correcting inaccurate public information. Feedback is grouped by theme and reported without identifying individuals. The programme measures participation across site types and neighbourhoods so that the pilot does not concentrate benefits only in locations with the easiest roofs or strongest administrative capacity."),
    ("Delivery risks", "Key risks include delayed grid approvals, roof defects discovered after survey, supplier lead times, incomplete meter data, contractor capacity, extreme weather and changes in grant conditions. Every risk has an owner, likelihood, impact, trigger, mitigation and review date. The project manager escalates risks that threaten safety, statutory compliance or the approved budget. Schedule recovery is not allowed to bypass engineering approval or commissioning checks. Where a site is unsuitable, the decision and evidence are recorded and the site is offered a practical alternative where possible."),
    ("Service and maintenance", "The maintenance desk triages alarms by safety, generation impact and urgency. Remote monitoring alerts are checked against meter data before a service visit is booked. Technicians record arrival time, fault symptoms, diagnostic steps, parts used, resolution and any follow-up action. Warranty claims retain supplier correspondence and evidence. The cooperative reviews recurring faults quarterly and uses the findings to improve procurement specifications, installer training and preventative maintenance. Sites receive an annual performance summary in accessible language."),
    ("Governance and reporting", "A monthly delivery board reviews cost, schedule, safety, quality, participation, generation and open decisions. Each decision has a named owner, evidence link, date and rationale. The board distinguishes facts, estimates and unresolved assumptions. Public reporting uses aggregated site information and explains exclusions. Independent sampling checks commissioning records and reported energy data. The programme closes the pilot only after outstanding defects, data gaps, training actions and financial reconciliations have an agreed disposition."),
]

LONG_TEXT = "\n\n".join(f"## {title}\n\n{body}\n\nImplementation note: {body} The site lead records evidence, the programme manager checks the control, and the monthly review confirms whether the action remains effective." for title, body in SECTIONS)

def write_text_files() -> None:
    (OUT / "northstar-programme.txt").write_text("NORTHSTAR COMMUNITY ENERGY — PILOT OPERATING BRIEF\n\n" + LONG_TEXT, encoding="utf-8")
    markdown = "# Northstar Community Energy\n\n> Long-form parser fixture · fictional programme · revision 1.0\n\n" + LONG_TEXT
    markdown += "\n\n## Decision register\n\n| ID | Decision | Owner | Status |\n|---|---|---|---|\n" + "\n".join(f"| DEC-{i:03d} | Review {title.lower()} controls | Programme manager | Open |" for i, (title, _) in enumerate(SECTIONS, 1))
    (OUT / "northstar-programme.md").write_text(markdown, encoding="utf-8")
    (OUT / "northstar-programme.markdown").write_text(markdown, encoding="utf-8")

def write_csv() -> None:
    path = OUT / "site-performance.csv"
    fields = ["site_id", "district", "site_type", "capacity_kw", "monthly_generation_kwh", "self_consumption_pct", "downtime_hours", "inspection_status", "report_month"]
    districts = ["North", "Central", "Riverside"]
    kinds = ["Library", "Clinic", "Community hall", "Workshop"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for i in range(1, 121):
            writer.writerow({"site_id": f"NS-{i:04d}", "district": districts[(i - 1) % 3], "site_type": kinds[(i - 1) % 4], "capacity_kw": round(8.5 + (i % 19) * 1.35, 2), "monthly_generation_kwh": 780 + (i * 137) % 2900, "self_consumption_pct": 42 + (i * 7) % 54, "downtime_hours": round((i % 6) * 0.7, 1), "inspection_status": "Passed" if i % 11 else "Action required", "report_month": f"2026-{(i % 12) + 1:02d}"})

def write_json() -> None:
    records = []
    for i in range(1, 81):
        records.append({"site_id": f"NS-{i:04d}", "district": ["North", "Central", "Riverside"][(i - 1) % 3], "asset": {"technology": "rooftop_pv", "capacity_kw": round(10 + (i % 17) * 1.25, 2), "inverter_count": 1 + i % 3}, "status": "operational" if i % 9 else "maintenance_review", "contacts": {"role": "site_coordinator", "email": f"coordinator{i:03d}@example.invalid"}, "controls": ["commissioning_record", "isolation_label", "warranty_register"], "notes": SECTIONS[i % len(SECTIONS)][1]})
    (OUT / "site-register.json").write_text(json.dumps({"schema_version": "1.0", "programme": "Northstar Community Energy", "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")

def write_html() -> None:
    cards = "\n".join(f"<section><h2>{title}</h2><p>{body}</p><p><strong>Control:</strong> retain evidence and review effectiveness at the monthly delivery board.</p></section>" for title, body in SECTIONS)
    rows = "\n".join(f"<tr><td>NS-{i:04d}</td><td>{['North','Central','Riverside'][(i-1)%3]}</td><td>{['Library','Clinic','Community hall','Workshop'][(i-1)%4]}</td><td>{8 + i % 20}.5</td><td>Operational</td></tr>" for i in range(1, 41))
    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Northstar programme handbook</title><style>body{{font-family:Arial;max-width:900px;margin:3rem auto;line-height:1.65}}table{{border-collapse:collapse}}td,th{{border:1px solid #aaa;padding:.5rem}}</style><script>window.neverExecute='fixture';</script></head><body><header><h1>Northstar Community Energy — Pilot handbook</h1><p>Long-form HTML extraction fixture, revision 1.0.</p></header>{cards}<h2>Site register sample</h2><table><thead><tr><th>Site</th><th>District</th><th>Type</th><th>kW</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table><footer><p>Fictional test data. No real site or person is represented.</p></footer></body></html>"
    (OUT / "programme-handbook.html").write_text(html, encoding="utf-8")

def write_pdf() -> None:
    doc = fitz.open()
    for title, body in SECTIONS:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(58, 55, 540, 105), title, fontsize=21, fontname="helv")
        page.insert_textbox(fitz.Rect(58, 125, 540, 760), (body + "\n\n" + body), fontsize=10.5, fontname="helv", lineheight=1.35)
    doc.set_metadata({"title": "Northstar Community Energy Pilot Brief", "author": "Context Studio fixture generator", "subject": "Long-form PDF parser fixture"})
    doc.save(OUT / "northstar-programme.pdf", garbage=4, deflate=True)
    doc.close()

def write_docx() -> None:
    doc = Document()
    doc.add_heading("Northstar Community Energy", 0)
    doc.add_paragraph("Pilot operating brief · Long-form DOCX parser fixture · Revision 1.0")
    for title, body in SECTIONS:
        doc.add_heading(title, level=1)
        doc.add_paragraph(body)
        doc.add_paragraph("Implementation control: retain source evidence, assign a named owner and verify the control during the monthly delivery review.")
    doc.add_heading("Site acceptance checklist", level=1)
    table = doc.add_table(rows=1, cols=4)
    for cell, value in zip(table.rows[0].cells, ["Control", "Evidence", "Owner", "Status"]): cell.text = value
    for item in ["Roof survey", "Electrical design", "Grid approval", "Commissioning", "Staff handover", "Warranty register", "Meter validation", "Safety close-out"]:
        cells = table.add_row().cells
        for cell, value in zip(cells, [item, f"{item} record and sign-off", "Site engineer", "Pending review"]): cell.text = value
    doc.save(OUT / "northstar-programme.docx")

def write_pptx() -> None:
    deck = Presentation()
    for index, (title, body) in enumerate(SECTIONS, 1):
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = f"{index:02d} · {title}"
        frame = slide.placeholders[1].text_frame
        frame.clear()
        frame.paragraphs[0].text = body
        frame.paragraphs[0].font.size = Pt(18)
        p = frame.add_paragraph()
        p.text = "Decision check: owner, evidence, trigger, review date and escalation path are recorded."
        p.font.size = Pt(14)
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Pilot delivery measures"
    box = slide.shapes.add_textbox(Inches(.8), Inches(1.5), Inches(8.5), Inches(4.5))
    box.text_frame.text = "Safety and quality before speed\nTransparent cost and schedule controls\nEvidence-linked energy reporting\nAccessible community participation\nMaintainable assets and clear ownership"
    deck.save(OUT / "northstar-programme.pptx")

def write_xlsx() -> None:
    book = Workbook()
    sites = book.active
    sites.title = "Site Register"
    sites.append(["Site ID", "District", "Site Type", "Capacity kW", "Generation kWh", "Self-use %", "Downtime h", "Inspection"])
    for i in range(1, 121):
        sites.append([f"NS-{i:04d}", ["North", "Central", "Riverside"][(i-1)%3], ["Library", "Clinic", "Community hall", "Workshop"][(i-1)%4], round(8.5+(i%19)*1.35,2), 780+(i*137)%2900, 42+(i*7)%54, round((i%6)*.7,1), "Passed" if i%11 else "Action required"])
    finance = book.create_sheet("Budget")
    finance.append(["Workstream", "Approved GBP", "Committed GBP", "Paid GBP", "Owner", "Control"])
    for i, name in enumerate(["Survey", "Engineering", "Modules", "Inverters", "Installation", "Grid connection", "Training", "Monitoring", "Maintenance", "Contingency"], 1):
        finance.append([name, 12000*i, 9500*i, 7200*i, "Finance lead", "Two-person approval and milestone evidence"])
    risks = book.create_sheet("Risk Register")
    risks.append(["Risk ID", "Description", "Likelihood", "Impact", "Owner", "Mitigation", "Review date"])
    for i, (title, body) in enumerate(SECTIONS, 1):
        risks.append([f"R-{i:03d}", title + ": " + body[:160], 2 + i%3, 3 + i%3, "Programme manager", "Track trigger, mitigation and evidence at monthly board", f"2026-{(i%12)+1:02d}-15"])
    for sheet in book.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(48, max(14, max(len(str(cell.value or "")) for cell in column[:30]) + 2))
    book.save(OUT / "northstar-programme.xlsx")

def main() -> None:
    write_text_files(); write_csv(); write_json(); write_html(); write_pdf(); write_docx(); write_pptx(); write_xlsx()
    print(f"Generated {len(list(OUT.iterdir()))} long-form fixtures in {OUT}")
    for path in sorted(OUT.iterdir()):
        if path.is_file(): print(f"{path.name}: {path.stat().st_size:,} bytes")

if __name__ == "__main__":
    main()
