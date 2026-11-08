from pathlib import Path

from docx import Document

from job_apply_agent.render import render_resume_docx

MD = """# Jane Doe
jane@example.com | +1 555 0100 | linkedin.com/in/janedoe

## Experience
### Data Analyst | 01/2024 – Present
*Acme Corp | Toronto, ON*
- Built **Power BI** dashboards for *finance*.

Plain paragraph with [a link](https://x.y) and \\| escaped pipe.
"""


def test_render_structure(tmp_path: Path):
    doc = Document(render_resume_docx(MD, tmp_path / "r.docx"))
    paras = doc.paragraphs
    assert paras[0].text == "JANE DOE"
    assert paras[2].text == "EXPERIENCE"
    assert paras[3].text == "Data Analyst\t01/2024 – Present"
    assert paras[4].text == "Acme Corp | Toronto, ON" and paras[4].runs[0].italic
    bullet = paras[5]
    assert bullet.style.name == "List Bullet"
    assert bullet.text == "Built Power BI dashboards for finance."
    assert any(r.bold and r.text == "Power BI" for r in bullet.runs)
    assert paras[6].text == "Plain paragraph with a link and | escaped pipe."


def test_contact_links_are_hyperlinks(tmp_path: Path):
    doc = Document(render_resume_docx(MD, tmp_path / "r.docx"))
    targets = {rel.target_ref for rel in doc.part.rels.values() if "hyperlink" in rel.reltype}
    assert targets == {"mailto:jane@example.com", "https://linkedin.com/in/janedoe"}
