from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'deliverables'
OUT.mkdir(exist_ok=True)
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
CN = '/System/Library/Fonts/STHeiti Light.ttc'
CNB = '/System/Library/Fonts/STHeiti Medium.ttc'

def diagram(lang):
    im = Image.new('RGB', (1600, 650), 'white')
    d = ImageDraw.Draw(im)
    ff = CN if lang == 'zh' else FONT
    fb = CNB if lang == 'zh' else BOLD
    title = ImageFont.truetype(fb, 31)
    body = ImageFont.truetype(ff, 27)
    small = ImageFont.truetype(ff, 24)
    ink = '#17394C'
    def arrow(points):
        d.line(points, fill=ink, width=4)
        (x0,y0),(x1,y1)=points[-2:]
        if x1>x0: tri=[(x1,y1),(x1-13,y1-8),(x1-13,y1+8)]
        elif y1>y0: tri=[(x1,y1),(x1-8,y1-13),(x1+8,y1-13)]
        else: tri=[(x1,y1),(x1+13,y1-8),(x1+13,y1+8)]
        d.polygon(tri,fill=ink)
    def box(x,y,w,h,txt):
        d.rounded_rectangle((x,y,x+w,y+h),radius=9,fill='#EEF4F7',outline='#AAC0CD',width=2)
        lines=txt.split('\n')
        for i,line in enumerate(lines):
            bounds=d.textbbox((0,0),line,font=body)
            d.text((x+(w-(bounds[2]-bounds[0]))/2,y+h/2-len(lines)*17+i*34-4),line,font=body,fill=ink)
    if lang=='zh':
        labs=['离线 Ingestion','API specs\n流程与业务规则','解析与校验\n保存来源和版本','完整记录\nWorkflow · API · Rule','生成 embedding','向量索引\n文本 + 向量 + 引用',
              '在线 RAG','用户问题与上下文','Workflow 向量检索','候选判断或澄清','按 ID 取完整资料','生成并校验示例','带来源的集成指南']
        note='相似度帮助发现候选；流程顺序、字段约束和绑定来自完整记录。'
    else:
        labs=['Offline ingestion','API specs\nWorkflows and rules','Parse and validate\nKeep source and version','Complete records\nWorkflow / API / Rule','Generate embeddings','Vector index\nText + vectors + references',
              'Online retrieval and generation','Question and context','Workflow vector search','Select or clarify','Fetch complete records','Generate and validate','Cited integration guide']
        note='Similarity discovers candidates. Complete records define order, constraints, and bindings.'
    d.text((25,8),labs[0],font=title,fill='black')
    box(25,65,360,105,labs[1]); box(440,65,420,105,labs[2]); box(920,65,640,105,labs[3])
    arrow([(385,117),(440,117)]); arrow([(860,117),(920,117)])
    d.text((330,220),labs[4],font=small,fill=ink)
    arrow([(650,170),(650,263),(920,263)])
    box(920,207,640,105,labs[5])
    d.text((25,340),labs[6],font=title,fill='black')
    box(25,395,450,76,labs[7]); box(565,395,450,76,labs[8]); box(1110,395,450,76,labs[9])
    arrow([(475,433),(565,433)]); arrow([(1015,433),(1110,433)])
    box(25,510,450,76,labs[10]); box(565,510,450,76,labs[11]); box(1110,510,450,76,labs[12])
    arrow([(1335,471),(1335,490),(12,490),(12,548),(25,548)])
    arrow([(475,548),(565,548)]); arrow([(1015,548),(1110,548)])
    d.text((25,610),note,font=small,fill='#445660')
    path=ROOT/f'pipeline-detailed-{lang}.png'; im.save(path)
    return path

def shade(cell,color):
    pr=cell._tc.get_or_add_tcPr()
    sh=OxmlElement('w:shd'); sh.set(qn('w:fill'),color); pr.append(sh)

def set_font(run,size=None,bold=None,color=None,code=False):
    run.font.name='Liberation Mono' if code else 'Arial'
    props=run._element.get_or_add_rPr()
    fonts=props.find(qn('w:rFonts'))
    if fonts is None:
        fonts=OxmlElement('w:rFonts'); props.insert(0,fonts)
    fonts.set(qn('w:eastAsia'),'Songti SC')
    if size: run.font.size=Pt(size)
    if bold is not None: run.bold=bold
    if color: run.font.color.rgb=RGBColor.from_string(color)

def inline(p,text,size=None,bold=None,color=None):
    pat=r'(\[[^\]]+\]\(https?://[^)]+\)|`[^`]+`|\*\*[^*]+\*\*)'
    for part in re.split(pat,text):
        if not part: continue
        link=re.fullmatch(r'\[([^\]]+)\]\((https?://[^)]+)\)',part)
        if link:
            h=OxmlElement('w:hyperlink'); h.set(qn('r:id'),p.part.relate_to(link[2],RT.HYPERLINK,is_external=True))
            r=OxmlElement('w:r'); rp=OxmlElement('w:rPr')
            c=OxmlElement('w:color');c.set(qn('w:val'),'24546A');rp.append(c)
            u=OxmlElement('w:u');u.set(qn('w:val'),'single');rp.append(u)
            f=OxmlElement('w:rFonts');f.set(qn('w:ascii'),'Arial');f.set(qn('w:eastAsia'),'Songti SC');rp.append(f)
            r.append(rp);t=OxmlElement('w:t');t.text=link[1];r.append(t);h.append(r);p._p.append(h)
        else:
            iscode=part.startswith('`')
            strong=part.startswith('**')
            t=part[1:-1] if iscode else part[2:-2] if strong else part
            r=p.add_run(t);set_font(r,size,True if strong else bold,color,code=iscode)

def table(doc,lines,lang):
    rows=[[c.strip() for c in line.strip().strip('|').split('|')] for line in lines]
    rows=[r for r in rows if not all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in r)]
    n=len(rows[0]); t=doc.add_table(rows=1,cols=n); t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=([1.38,2.72,2.9] if n==3 else [3.05,3.95])
    for c,w in zip(t.columns,widths):c.width=Inches(w)
    for ridx,row in enumerate(rows):
        cells=t.rows[0].cells if ridx==0 else t.add_row().cells
        pr=t.rows[ridx]._tr.get_or_add_trPr()
        no=OxmlElement('w:cantSplit');pr.append(no)
        if ridx==0:
            repeat=OxmlElement('w:tblHeader');pr.append(repeat)
        for i,(cell,value) in enumerate(zip(cells,row)):
            cell.width=Inches(widths[i]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp=cell._tc.get_or_add_tcPr(); mar=OxmlElement('w:tcMar')
            for side,v in [('top',80),('bottom',80),('left',95),('right',95)]:
                e=OxmlElement('w:'+side);e.set(qn('w:w'),str(v));e.set(qn('w:type'),'dxa');mar.append(e)
            cp.append(mar);b=OxmlElement('w:tcBorders')
            for side in ['top','left','bottom','right']:
                e=OxmlElement('w:'+side);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');b.append(e)
            cp.append(b)
            shade(cell,'24485C' if ridx==0 else ('F0F5F8' if ridx%2==0 else 'FFFFFF'))
            p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(0)
            p.paragraph_format.line_spacing=Pt(14) if lang=='zh' else 1.08
            if len(rows)<=5 and ridx<len(rows)-1:
                p.paragraph_format.keep_with_next=True
            inline(p,value,10 if lang=='zh' else 9.6,ridx==0,'FFFFFF' if ridx==0 else '000000')
    doc.add_paragraph().paragraph_format.space_after=Pt(0)

def build(lang):
    src=ROOT/f'proposal-detailed-{lang}.md'; lines=src.read_text().splitlines()
    doc=Document();sec=doc.sections[0]
    sec.page_width=Inches(8.5);sec.page_height=Inches(11)
    sec.top_margin=Inches(.7);sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.75)
    sec.footer_distance=Inches(.3)
    for s in doc.styles:
        for border in list(s._element.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    for name in ['Normal','Title','Heading 1','Heading 2','Heading 3','List Bullet','List Number','Caption']:
        s=doc.styles[name];s.font.name='Arial';s.font.color.rgb=RGBColor(0,0,0)
        s._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Songti SC')
    norm=doc.styles['Normal'];norm.font.size=Pt(11)
    norm.paragraph_format.line_spacing=Pt(17) if lang=='zh' else 1.12
    norm.paragraph_format.space_after=Pt(6)
    for name,size,before,after in [('Title',24,0,12),('Heading 1',16,16,8),('Heading 2',12,10,5)]:
        s=doc.styles[name];s.font.size=Pt(size);s.font.bold=True
        s.paragraph_format.space_before=Pt(before);s.paragraph_format.space_after=Pt(after);s.paragraph_format.keep_with_next=True
    foot=sec.footer.paragraphs[0];foot.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    r=foot.add_run();set_font(r,9,color='555555');fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');r._r.addnext(fld)
    doc.core_properties.title='API 接入助手详细技术方案' if lang=='zh' else 'API Integration Assistant Technical Proposal'
    doc.core_properties.subject='Ingestion, vector retrieval, workflow lookup, and prototype design'
    doc.core_properties.author=''
    i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1;continue
        if line.startswith('```'):
            code=[];i+=1
            if doc.paragraphs:
                doc.paragraphs[-1].paragraph_format.keep_with_next=True
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            p=doc.add_paragraph();p.paragraph_format.left_indent=Inches(.12)
            p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(8);p.paragraph_format.line_spacing=1.05
            p.paragraph_format.keep_together=True
            set_font(p.add_run('\n'.join(code)),9,code=True)
        elif line.startswith('|'):
            block=[]
            while i<len(lines) and lines[i].strip().startswith('|'):block.append(lines[i]);i+=1
            table(doc,block,lang);continue
        elif line.startswith('!['):
            m=re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            p=doc.add_paragraph();p.paragraph_format.space_before=Pt(3);p.paragraph_format.space_after=Pt(8)
            p.paragraph_format.line_spacing=1.0
            pic=p.add_run().add_picture(str(ROOT/m[2]),width=Inches(7))
            pic._inline.docPr.set('descr',m[1])
        elif line.startswith('# '):
            p=doc.add_paragraph(style='Title');inline(p,line[2:])
        elif line.startswith('## '):
            p=doc.add_paragraph(style='Heading 1');inline(p,line[3:])
        elif line.startswith('### '):
            p=doc.add_paragraph(style='Heading 2');inline(p,line[4:])
        elif line.startswith('- '):
            p=doc.add_paragraph(style='List Bullet');inline(p,line[2:])
        elif re.match(r'^\d+\. ',line):
            p=doc.add_paragraph();p.paragraph_format.left_indent=Inches(.23);p.paragraph_format.first_line_indent=Inches(-.23);inline(p,line)
        else:
            p=doc.add_paragraph();inline(p,line)
        i+=1
    name='API接入助手详细技术方案.docx' if lang=='zh' else 'API-Integration-Assistant-Technical-Proposal.docx'
    out=OUT/name;doc.save(out);print(str(out))
    (OUT/('方案中文讲解.md' if lang=='zh' else 'Technical-Proposal.md')).write_text(src.read_text().replace('(pipeline-detailed-'+lang+'.png)', '(../work/pipeline-detailed-'+lang+'.png)'))

for lang in ['zh','en']:
    diagram(lang)
    build(lang)
