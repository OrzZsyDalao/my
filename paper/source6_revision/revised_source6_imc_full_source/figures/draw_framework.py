"""Rebuild Figure 1 as editable SVG and vector PDF; no experimental values."""
from pathlib import Path
from html import escape
from math import atan2,cos,sin
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parent
W,H=740,322
c=canvas.Canvas(str(ROOT/'framework_cross_layer_audit.pdf'),pagesize=(W,H))
c.setTitle('CLASP: from shared observations to paired distributions')
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
INK='#203447';GRAY='#526575';EDGE='#B9C8D3';BLUE='#24668E';ORANGE='#A44E1D';GREEN='#21685D'
def box(x,y,w,h,fill='white',stroke=EDGE):
 c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke));c.setLineWidth(.8);c.roundRect(x,H-y-h,w,h,5,fill=1,stroke=1)
 svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width=".8"/>')
def txt(x,y,s,size=11,color=INK,bold=False):
 c.setFont('Helvetica-Bold' if bold else 'Helvetica',size);c.setFillColor(HexColor(color));c.drawString(x,H-y-size,s)
 svg.append(f'<text x="{x}" y="{y+size}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(s)}</text>')
def arrow(points,color=GRAY,dash=False):
 c.setStrokeColor(HexColor(color));c.setLineWidth(1.2);c.setDash([3,2] if dash else [])
 p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
 for x,y in points[1:]:p.lineTo(x,H-y)
 c.drawPath(p);c.setDash([])
 svg.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="1.2"'+(' stroke-dasharray="3 2"' if dash else '')+'/>')
 x,y=points[-1];xx,yy=points[-2];a=atan2(y-yy,x-xx)
 pts=[(x,y),(x-5*cos(a)+2.5*sin(a),y-5*sin(a)-2.5*cos(a)),(x-5*cos(a)-2.5*sin(a),y-5*sin(a)+2.5*cos(a))]
 p=c.beginPath();p.moveTo(pts[0][0],H-pts[0][1])
 for xx,yy in pts[1:]:p.lineTo(xx,H-yy)
 p.close();c.setFillColor(HexColor(color));c.drawPath(p,fill=1,stroke=0)
 svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in pts)+f'" fill="{color}"/>')

txt(12,4,'CLASP',14,bold=True)
txt(67,7,'One country-measurement unit; paired comparison over the same segments',11)
box(12,31,149,45,'#F3F6F8');txt(21,38,'Traceroutes + probe metadata',10,bold=True);txt(21,54,'Hop locations, ASNs, RTTs',10)
box(184,31,166,45,'#F3F6F8');txt(193,38,'Cable / landing-point inventory',10,bold=True);txt(193,54,'Lifecycle + geographic constraints',10)
box(372,31,171,45,'#F3F6F8');txt(381,38,'Allocation evidence',10,bold=True);txt(381,54,'Proximity, AS context, RTT',10)
arrow([(86,76),(86,94)]);arrow([(267,76),(267,94)])

box(12,94,149,145,'#F7F9FB');txt(22,104,'1  Extract segments',12,bold=True);txt(22,122,'Section III-B',10,GRAY)
txt(22,148,'Successive visible hops',11);txt(22,166,'Network-transition label',11);txt(22,184,'Trace identity retained',11)
txt(22,214,'All valid traces retained',10,GRAY)

box(184,94,166,145,'#FFF8F0');txt(194,104,'2  Feasible support',12,bold=True);txt(194,122,'Sections III-C / III-E',10,GRAY)
txt(194,148,'Landing-region corridors',11);txt(194,166,'Geography, lifecycle, RTT',11);txt(194,184,'Candidate set + map state',11)
txt(194,214,'Candidate-bearing segments',10,ORANGE)
arrow([(161,171),(184,171)])

box(372,94,171,145,'#F7FAFB');txt(382,104,'3  Paired distributions',12,bold=True);txt(382,122,'Sections III-D / III-F',10,GRAY)
box(382,145,151,34,'#EAF3F9',BLUE);txt(390,150,'Network transitions',11,BLUE,True);txt(390,165,'Count each segment once',9.8,BLUE)
box(382,184,151,34,'#FFF1E4',ORANGE);txt(390,189,'Corridor support',11,ORANGE,True);txt(390,204,'Allocate unit mass to candidates',9.3,ORANGE)
txt(382,223,'Same segments; equal total mass',9.6,bold=True)
# The candidate-bearing cohort feeds BOTH distributions; evidence feeds allocation only.
arrow([(350,171),(363,171),(363,161),(382,161)],BLUE)
arrow([(363,171),(363,201),(382,201)],ORANGE)
arrow([(458,76),(552,76),(552,201),(533,201)],ORANGE,True)

box(565,94,163,145,'#F2F8F5');txt(575,104,'4  Compare layers',12,bold=True);txt(575,122,'Section III-G',10,GRAY)
txt(575,147,'Within each unit',11,GREEN,True);txt(575,163,'Concentration + breadth',10.4)
txt(575,184,'Across units',11,GREEN,True);txt(575,200,'Layer Agreement',11)
txt(575,221,'Spearman rank association',9.6,GRAY)
arrow([(543,171),(565,171)])

box(184,268,544,42,'#F7F4FA','#B3A5C2')
txt(195,274,'Separate trace-level output: submarine exposure',11,'#65517B',True)
txt(195,291,'Traces with an inter-region candidate / all valid traces',10.5,'#65517B')
arrow([(86,239),(86,289),(184,289)],'#65517B')
arrow([(267,239),(267,268)],'#65517B',True)
txt(279,247,'Inter-region candidate flags',9.8,'#65517B')
txt(12,297,'Solid: main flow',9.1,GRAY)
txt(12,309,'Dashed: inputs / flags',8.8,GRAY)

c.showPage();c.save();svg.append('</svg>')
(ROOT/'framework_cross_layer_audit.svg').write_text('\n'.join(svg),encoding='utf-8')
print(ROOT/'framework_cross_layer_audit.pdf')
