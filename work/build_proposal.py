from pathlib import Path
from datetime import datetime, timezone
import re

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
WORK = ROOT / "work"
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

TITLE = "API Integration Assistant"
SUBTITLE = "Proposed ingestion and retrieval design"
INTRO = (
    "Use LangChain to turn a customer's business request into an integration guide: "
    "the applicable workflow, ordered API calls, relevant fields, value sources, "
    "request examples and source references. The first prototype provides guidance "
    "for fictional APIs; live API execution is outside its proposed scope."
)

SECTIONS = [
    ("Ingestion pipeline", [
        "On initial load and source changes, parse API specifications, resolve schema references, "
        "and preserve request parameters and request/response schemas. Normalize supplied workflows "
        "and business rules into reviewed records with applicability conditions, ordered steps, "
        "branches, field rules and output-to-input bindings. Flag missing or conflicting definitions.",
        "Keep original sources and complete records with versions and source locations. Embed "
        "workflow descriptions and API/rule passages into a local vector store, with record IDs, "
        "document types, workflow/API references, versions and sources. Refresh affected records "
        "and embeddings on updates. "
        "The prototype uses JSON/YAML for canonical records plus a local vector index."
    ]),
    ("Prompt lookup and answer generation", [
        "1. Retrieve and select. Embed the prompt with relevant conversation context. Search records "
        "with document_type=workflow, filtering by known conditions and active workflow versions. "
        "The LLM checks candidate applicability and returns a known ID, clarification, or no match. "
        "Validate its selection; similarity alone does not establish a supported match.",
        "2. Fetch complete evidence. Read the selected workflow by ID and version. Fetch every "
        "referenced operation by API identity, version and operationId, including resolved schemas, "
        "linked rules and examples. Apply documented branches and data bindings. Scope any "
        "supplementary passage search to the selected workflow and API versions.",
        "3. Generate and check. Combine API-required fields with scenario rules. Explain values from "
        "user input, allowed enums, configuration and earlier responses. Generate ordered calls and "
        "synthetic payloads with citations. Check required fields, schema constraints and encoded "
        "workflow rules; report unsupported or conflicting evidence. Schema checks do not prove "
        "successful execution."
    ]),
    ("Prototype and acceptance", [
        "Use personal and business account-opening workflows over three fictional operations: "
        "createCustomer → verifyIdentity → createAccount. Pass customerId forward; require "
        "successful verification. Distinguish company-only fields while preserving schema-required "
        "inputs. Log retrieved candidate IDs to demonstrate vector lookup.",
        "Through a minimal chat UI, demonstrate a supported request with the correct sequence, "
        "field/value explanations and valid examples; clarification for an incomplete request; "
        "and an explicit no-match result for an unsupported request. Expose source versions and "
        "output-to-input mappings in the answer."
    ]),
    ("Implementation and decisions to confirm", [
        "Use a fixed LangChain retrieval and generation chain. Search and fetch functions can also "
        "be exposed as tools; add MCP when multiple clients need access. The registry supplies "
        "ordering; the vector index supplies candidates.",
        "Confirm the first scenario and authoritative specs/rules; who reviews workflow order and "
        "exceptions; approved chat/embedding models, storage and UI; and whether executable mock "
        "requests are required."
    ]),
]


def diagram(path: Path):
    # Two aligned process lanes; diagram text remains legible at the printed width.
    im = Image.new("RGB", (1800, 240), "white")
    d = ImageDraw.Draw(im)
    regular = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 29)
    ink = "#172B3A"
    border = "#8FA3AF"
    fill = "#F2F6F8"

    def arrow(x1, y, x2):
        d.line((x1, y, x2-11, y), fill=ink, width=3)
        d.polygon([(x2-13, y-7), (x2, y), (x2-13, y+7)], fill=ink)

    def box(x, y, w, text):
        d.rounded_rectangle((x, y, x+w, y+75), radius=5, fill=fill, outline=border, width=2)
        lines = text.split("\n")
        line_h = 32
        top = y + (75-len(lines)*line_h)/2 - 1
        for j, line in enumerate(lines):
            bounds = d.textbbox((0,0), line, font=regular)
            tw = bounds[2]-bounds[0]
            d.text((x+(w-tw)/2, top+j*line_h), line, fill=ink, font=regular)

    d.text((0, 43), "INGEST", font=bold, fill=ink)
    box(170, 20, 410, "Specs, rules, workflows")
    arrow(590, 58, 655)
    box(665, 20, 410, "Parse, validate and embed")
    arrow(1085, 58, 1150)
    box(1160, 20, 620, "Canonical records + vector index")

    # Both candidate search and exact retrieval consume the prepared knowledge store.
    d.line((1470, 95, 1470, 114, 622, 114), fill=border, width=2)
    for branch_x in (622, 957):
        d.line((branch_x, 114, branch_x, 126), fill=border, width=2)
        d.polygon([(branch_x-6, 125), (branch_x+6, 125), (branch_x, 134)], fill=border)

    d.text((0, 157), "ANSWER", font=bold, fill=ink)
    boxes = [
        (170, 245, "Embed prompt"),
        (480, 285, "Search + select"),
        (830, 255, "Fetch by IDs"),
        (1150, 300, "Generate + check"),
        (1515, 265, "Cited guide"),
    ]
    for i, (x, w, text) in enumerate(boxes):
        box(x, 135, w, text)
        if i < len(boxes)-1:
            arrow(x+w+10, 173, boxes[i+1][0]-10)
    im.save(path)


def set_font(style, size, bold=False):
    style.font.name = "Arial"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    for color in list(rpr.findall(qn("w:color"))):
        for attr in ("w:themeColor", "w:themeTint", "w:themeShade"):
            color.attrib.pop(qn(attr), None)
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:"+key), "Arial")
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn("w:"+key), None)


doc = Document()
sec = doc.sections[0]
sec.page_width = Inches(8.5)
sec.page_height = Inches(11)
sec.top_margin = Inches(0.55)
sec.bottom_margin = Inches(0.55)
sec.left_margin = Inches(0.65)
sec.right_margin = Inches(0.65)

set_font(doc.styles["Normal"], 10.3)
normal = doc.styles["Normal"].paragraph_format
normal.line_spacing = 1.05
normal.space_after = Pt(4)
normal.widow_control = True
set_font(doc.styles["Title"], 20, bold=True)
doc.styles["Title"].paragraph_format.space_after = Pt(2)
set_font(doc.styles["Subtitle"], 10.5)
doc.styles["Subtitle"].paragraph_format.space_after = Pt(7)
set_font(doc.styles["Heading 1"], 11.2, bold=True)
doc.styles["Heading 1"].paragraph_format.space_before = Pt(7)
doc.styles["Heading 1"].paragraph_format.space_after = Pt(3)
doc.styles["Heading 1"].paragraph_format.keep_with_next = True

for style_name in ("Normal", "Title", "Subtitle", "Heading 1"):
    ppr = doc.styles[style_name].element.find(qn("w:pPr"))
    if ppr is not None:
        for border in list(ppr.findall(qn("w:pBdr"))):
            ppr.remove(border)

doc.add_paragraph(TITLE, "Title")
doc.add_paragraph(SUBTITLE, "Subtitle")
doc.add_paragraph(INTRO)
diag = WORK / "pipeline.png"
diagram(diag)
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(1)
p.add_run().add_picture(str(diag), width=Inches(7.2))
shape = doc.inline_shapes[-1]
shape._inline.docPr.set("descr", "Ingestion parses specs, rules and workflows and stores canonical records plus a vector index. The answer pipeline embeds the prompt, retrieves workflow candidates, selects or clarifies, fetches complete records by ID, and generates and checks a cited guide.")

for heading, paragraphs in SECTIONS:
    doc.add_paragraph(heading, "Heading 1")
    for text in paragraphs:
        doc.add_paragraph(text)

props = doc.core_properties
props.title = TITLE
props.subject = SUBTITLE
props.author = ""
props.last_modified_by = ""
props.created = datetime(2026, 11, 10, tzinfo=timezone.utc)
props.modified = props.created
props.comments = ""
target = OUT / "API-Integration-Assistant-One-Page.docx"
doc.save(target)

md = ["# "+TITLE, SUBTITLE, INTRO]
for heading, paragraphs in SECTIONS:
    md.extend(["## "+heading, *paragraphs])
(WORK / "proposal-content.md").write_text("\n\n".join(md)+"\n", encoding="utf-8")
word_count = len(re.findall(r"\S+", " ".join([INTRO]+[p for _,ps in SECTIONS for p in ps])))
print(f"Saved {target}\nBody words: {word_count}")
