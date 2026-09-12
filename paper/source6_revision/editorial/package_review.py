"""Check preserved material and generate a readable manuscript and edit record."""
from pathlib import Path
import re
import json
import collections
import hashlib
import difflib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['IEEE-conference-template-062824.tex'] + [
    'files/' + p.name for p in sorted((ROOT/'files').glob('*.tex'))]
checks = []
patterns = {
    'numeric_token_multiset': r'(?<![A-Za-z])\d+(?:[,.:]\d+)*',
    'citation_sequence': r'\\cite\{([^}]+)\}',
    'label_sequence': r'\\label\{([^}]+)\}',
    'reference_multiset': r'\\(?:eqref|ref)\{([^}]+)\}',
    'math_sequence': r'\\\(.*?\\\)|\\\[.*?\\\]|\\begin\{equation\}.*?\\end\{equation\}',
    'float_sequence': r'\\begin\{(?:figure\*?|table\*?)\}.*?\\end\{(?:figure\*?|table\*?)\}',
    'heading_sequence': r'\\(?:section|subsection|paragraph)\{([^}]+)\}',
}
diffs = []
for file in FILES:
    before = (ROOT/'original'/file).read_text(encoding='utf-8')
    after = (ROOT/file).read_text(encoding='utf-8')
    result = {'file':file, 'before_sha256':hashlib.sha256(before.encode()).hexdigest(),
              'after_sha256':hashlib.sha256(after.encode()).hexdigest()}
    for key, pattern in patterns.items():
        a, b = re.findall(pattern,before,re.S), re.findall(pattern,after,re.S)
        result[key] = collections.Counter(a)==collections.Counter(b) if key.endswith('multiset') else a==b
    checks.append(result)
    diffs.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                    fromfile='original/'+file,tofile=file))
assert all(row[key] for row in checks for key in patterns), checks
(ROOT/'editorial/revision.diff').write_text(''.join(diffs),encoding='utf-8')

main=(ROOT/FILES[0]).read_text(encoding='utf-8')
parts=re.findall(r'\\input\{([^}]+)\}',main)
body='\n\n'.join((ROOT/(p+'.tex')).read_text(encoding='utf-8') for p in parts)
abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',main,re.S).group(1).strip()
alltext=abstract+'\n\n'+body
citeorder=[]
for group in re.findall(r'\\cite\{([^}]+)\}',alltext):
    for key in group.split(','):
        if key not in citeorder: citeorder.append(key)
citations={key:i+1 for i,key in enumerate(citeorder)}

# Assign display numbers in unchanged LaTeX source order.
labels={}; section=0; sub=0; figure=0; table=0; equation=0
for m in re.finditer(r'\\section\{[^}]+\}|\\subsection\{[^}]+\}|\\begin\{(?:figure\*?|table\*?|equation)\}.*?\\end\{(?:figure\*?|table\*?|equation)\}|\\label\{[^}]+\}',body,re.S):
    block=m.group()
    if block.startswith('\\section'):
        section+=1; sub=0
    elif block.startswith('\\subsection'):
        sub+=1
    elif block.startswith('\\begin'):
        if block.startswith('\\begin{figure'):
            figure+=1; number=str(figure)
            for letter,sm in zip('abcdefghijklmnopqrstuvwxyz',re.finditer(r'\\subfloat\[(.*?)\]\{',block,re.S)):
                for label in re.findall(r'\\label\{([^}]+)\}',sm.group(1)): labels[label]=number+'('+letter+')'
        elif block.startswith('\\begin{table'):
            table+=1; number=['I','II','III','IV','V','VI','VII','VIII'][table-1]
        else:
            equation+=1; number=str(equation)
        for label in re.findall(r'\\label\{([^}]+)\}',block): labels.setdefault(label,number)
    else:
        label=re.search(r'\\label\{([^}]+)\}',block).group(1)
        labels[label]=['','I','II','III','IV','V','VI','VII','VIII'][section]+('.'+chr(64+sub) if sub else '')

def plain(text):
    text=re.sub(r'(?<=\w)-\s*\n\s*(?=[a-z])','-',text)
    text=re.sub(r'\\label\{[^}]+\}','',text)
    text=re.sub(r'\\cite\{([^}]+)\}',lambda m:'['+', '.join(str(citations[k]) for k in m.group(1).split(','))+']',text)
    text=re.sub(r'\\eqref\{([^}]+)\}',lambda m:'('+labels[m.group(1)]+')',text)
    text=re.sub(r'\\ref\{([^}]+)\}',lambda m:labels[m.group(1)],text)
    text=text.replace('\\%','%').replace('~',' ').replace('\\ ',' ')
    text=re.sub(r'\\(?:textbf|emph|texttt)\{([^{}]+)\}',lambda m:m.group(1),text)
    text=text.replace('\\(','$').replace('\\)','$')
    return text

float_index=0
def convert_float(m):
    global float_index
    block=m.group(); caption=re.search(r'\\caption\{([^}]+)\}',block).group(1)
    labs=re.findall(r'\\label\{([^}]+)\}',block)
    final_label=labs[-1]; number=labels[final_label]
    if block.startswith('\\begin{figure'):
        out='\n\n**Figure '+number+'. '+caption+'**\n\n'
        images=re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',block)
        for i,image in enumerate(images):
            lead='('+chr(97+i)+') ' if len(images)>1 else ''
            out+='['+lead+'Original figure PDF]('+image+')\n\n'
        return out
    # All manuscript tables use a single tabular environment and no row spans.
    tab=re.search(r'\\begin\{tabular\}[^\n]*\n(.*?)\\end\{tabular\}',block,re.S).group(1)
    tab=re.sub(r'\\(?:toprule|midrule|bottomrule)','',tab)
    rows=[]
    for row in tab.split('\\\\'):
        row=plain(row).strip()
        if row: rows.append([re.sub(r'\s+',' ',c).strip() for c in row.split('&')])
    out='\n\n**Table '+number+'. '+caption+'**\n\n'
    for i,row in enumerate(rows):
        out+='| '+' | '.join(c.replace('|',r'\vert ') for c in row)+' |\n'
        if i==0: out+='| '+' | '.join(['---']*len(row))+' |\n'
    return out+'\n'

readable=re.sub(r'\\begin\{(?:figure\*?|table\*?)\}.*?\\end\{(?:figure\*?|table\*?)\}',convert_float,alltext,flags=re.S)
def display_equation(m):
    label=re.search(r'\\label\{([^}]+)\}',m.group(1))
    formula=re.sub(r'\\label\{[^}]+\}','',m.group(1)).strip()
    tag='\\tag{'+labels[label.group(1)]+'}' if label else ''
    return '\n\n$$\n'+formula+'\n'+tag+'\n$$\n\n'
readable=re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}',display_equation,readable,flags=re.S)
readable=readable.replace('\\[','\n\n$$\n').replace('\\]','\n$$\n\n')
sec=[0,0]
def heading(m):
    kind,title=m.group(1),m.group(2)
    if kind=='section':
        sec[0]+=1;sec[1]=0
        return '## '+['','I','II','III','IV','V','VI','VII','VIII'][sec[0]]+'. '+title
    if kind=='subsection':
        sec[1]+=1
        return '### '+chr(64+sec[1])+'. '+title
    return '**'+title+'**'
readable=re.sub(r'\\(section|subsection|paragraph)\{([^}]+)\}',heading,readable)
readable=plain(readable)
# Join source wrapping, retaining markdown block/table/math boundaries.
blocks=[]
for paragraph in readable.split('\n\n'):
    if not paragraph.strip(): continue
    if paragraph.lstrip().startswith(('|','$$')): blocks.append(paragraph.strip())
    else: blocks.append(re.sub(r'\s*\n\s*',' ',paragraph).strip())
readable='\n\n'.join(blocks)

# Preserve bibliography content while rendering fields in citation order.
bib=(ROOT/'refs.bib').read_text(encoding='utf-8')
entries={}
for match in re.finditer(r'@\w+\{([^,]+),',bib):
    start=match.end(); depth=1; i=start
    while i<len(bib) and depth:
        if bib[i]=='{': depth+=1
        if bib[i]=='}': depth-=1
        i+=1
    entries[match.group(1)]=bib[start:i-1]
def field(entry,key):
    match=re.search(r'\b'+key+r'\s*=\s*\{',entry,re.I)
    if not match:return ''
    i=match.end();start=i;depth=1
    while i<len(entry) and depth:
        if entry[i]=='{':depth+=1
        if entry[i]=='}':depth-=1
        i+=1
    return entry[start:i-1]
refs=[]
for key in citeorder:
    entry=entries[key]
    vals=[field(entry,k) for k in ['author','title','journal','booktitle','year','pages','howpublished']]
    text='. '.join(v for v in vals if v)
    text=re.sub(r'\\url\{([^}]+)\}',r'\1',text)
    text=text.replace("{\\'a}",'á').replace("{\\'e}",'é').replace("{\\'o}",'ó')
    text=text.replace('{','').replace('}','').replace('--','–')
    refs.append(f'[{citations[key]}] {text}.')
title='When Network Diversity Narrows at Sea: A Cross-Layer View of Internet Service Paths'
keywords=re.sub(r'\s+',' ',re.search(r'\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}',main,re.S).group(1)).strip()
readable=readable.replace('## I. Introduction','**Keywords:** '+keywords+'\n\n## I. Introduction',1)
(ROOT/'MANUSCRIPT_REVISED.md').write_text('# '+title+'\n\n**Abstract**\n\n'+readable+'\n\n## References\n\n'+'\n\n'.join(refs)+'\n',encoding='utf-8')

changes=json.loads((ROOT/'editorial/changes.json').read_text(encoding='utf-8'))
notes=['# Source6 全文修改对照与理由','本轮修改以原压缩包为基准。以下对应 75 处段落级修改，原文与修订文保留 LaTeX 标记以便准确比对。正文没有新增实验、文献或数据。原稿中需作者判断的问题单列于 REVIEW_LOCATIONS.md。',
       '每项均列出修改位置、原文、修订文、修改理由和作用。行号对应本次修订后的源文件。']
for change in changes:
    text=(ROOT/change['file']).read_text(encoding='utf-8')
    pos=text.find(change['after'])
    assert pos>=0
    line=text[:pos].count('\n')+1
    change['line']=line
    notes += [f"## {change['id']} · {change['file']}:{line}",
              '**原文**\n\n```latex\n'+change['before']+'\n```',
              '**修订文**\n\n```latex\n'+change['after']+'\n```',
              '**为什么修改：** '+change['reason'],
              '**意义与改进：** '+change['benefit']]
(ROOT/'REVISION_NOTES_CN.md').write_text('\n\n'.join(notes)+'\n',encoding='utf-8')
(ROOT/'editorial/changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')

issues=[
('IEEE-conference-template-062824.tex','showing that service selection',
 '摘要由测量组差异推至 service selection and deployment must be retained，并以 shapes 描述 deployment/target selection 的作用。现有比较的目标总体不同；这些因果或必要性措辞的证据强度需作者确认。原判断保留。'),
('files/2-background.tex','these logical paths depend',
 '对 geographically separated regions 的路径统一使用 depend on submarine cables。该句范围与是否存在其他物理连接解释之间的关系未在本段说明；原句判断保留。'),
('files/3-framework.tex','A candidate is',
 'Geographic and delay feasibility 使用相邻可见 hop 的 RTT 差作候选可行性条件。正文未在此给出该差分对应物理往返传播下界的条件或验证；公式及判断原样保留。'),
('files/3-framework.tex','Direction is preserved throughout',
 '这里的 Direction is preserved throughout the aggregation 与前文 direction-independent corridor 可能产生歧义。所在段讨论 network-side distribution，但 throughout 的指代范围需作者确认；未改写。'),
('files/5-result.tex','Country-matched comparisons show',
 '国家匹配保留了源国家，但测量目标总体发生变化。此处与摘要、讨论中的部署解释如何对应，需要作者确认；本轮未增加探针或目标层面的控制事实。'),
('files/5-result.tex','Contraction is a recurring',
 '四类结果使用论文的 Top-2=80% 分类。与仓库 paper_primary_units.csv 逐行比较，28 行分类标签不同，连续字段一致；仓库分类函数使用混合分级。81 个收缩单位相同，其他类别不同。正文原有四类计数全部保留。'),
('files/5-result.tex','Repeated overlap among bounded',
 '原文使用 produces 将候选重叠与案例聚合分布连接。本轮只将该句提前；未补充独立的重叠分解、机制检验或最坏情形证明。'),
('files/6-measurement-scope-and-implications.tex','The paired view distinguishes',
 '关于部署更近实例、改变互联、增加不同登陆区域接入的两项 can 判断属于原稿的干预含义。本轮未增加实际干预实验或效果数据，原强度保留。'),
('files/6-measurement-scope-and-implications.tex','To assess resolution sensitivity',
 '原稿称 mean Jaccard 1.0 隔离 corridor grouping resolution。仓库敏感性结果在直径变化时，进入主要分布的片段数及审计单位数也变化；且该结果来自 A-Root 子集。原段与数字原样保留，未替作者修正其解释。'),
('files/6-measurement-scope-and-implications.tex','The single-corridor share is',
 '原稿按 10–30 km 顺序列出 46.2%、47.4%、54.8%。仓库敏感性 CSV 的 10 km 与 20 km 对应值顺序相反。正文没有交换或改写这些数字，供作者确认来源版本。'),
('files/4-datasets.tex','All inputs are aligned',
 '原稿将全部辅助数据表述为与 July 1, 2026 对齐。当前材料中的版本标签与实际文件获取时间、有效期和完整来源链需要一一对应；本轮未替作者增加来源事实。'),
('files/6-measurement-scope-and-implications.tex','The released',
 '原文说发布材料 reconstruct 主表与图。仓库记录存在部分阶段提交 unknown、生成时工作树 dirty 及分类不一致。这里只定位复现表述的对应位置；不将本轮文本静态核对写成全流程复现。'),
('files/2-background.tex','Calypso combines',
 '此处及 refs.bib 仍为 wang2025calypso。遵守本轮不新增文献与保留引文编号的要求，未替换成 2026 长文，也未加入其新功能或验证结果。'),
]
locs=['# 需作者确认的位置','本清单与修订正文分开。原稿数字、方法和判断强度按要求保留；此处仅定位材料对应、逻辑或证据问题，不把未提供事实写入论文。']
for i,(file,anchor,note) in enumerate(issues,1):
    txt=(ROOT/file).read_text(encoding='utf-8');pos=txt.find(anchor);assert pos>=0,(file,anchor)
    line=txt[:pos].count('\n')+1
    locs += [f'## Q{i:02} · {file}:{line}',f'**定位片段：** `{anchor}`',note]
(ROOT/'REVIEW_LOCATIONS.md').write_text('\n\n'.join(locs)+'\n',encoding='utf-8')

assets={}
baseline_path=Path('C:/Users/13578/Downloads/When_Network_Diversity_Narrows_at_Sea_INFOCOM2027_Source6 (1).zip')
if baseline_path.exists():
    with zipfile.ZipFile(baseline_path) as archive:
        for name in archive.namelist():
            if name.startswith('figures/') or name in ['refs.bib','IEEEtran.cls','IEEEtran.bst']:
                assets[name]=hashlib.sha256(archive.read(name)).hexdigest()==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    assert all(assets.values())
report={'baseline':'When_Network_Diversity_Narrows_at_Sea_INFOCOM2027_Source6 (1).zip',
        'paragraph_edits':len(changes),'checks':checks,'citation_order':citations,
        'label_numbers':labels,'supporting_asset_checks':assets,
        'verification_scope':'Static source and paragraph review; no LaTeX compilation or full experiment rerun.',
        'semantic_review':'Modal and causal strength reviewed against each original paragraph; logical/evidence questions are separate, not repaired by inserting claims.'}
(ROOT/'editorial/preservation_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
bundle_files=[ROOT/'IEEE-conference-template-062824.tex',ROOT/'refs.bib',ROOT/'IEEEtran.cls',ROOT/'IEEEtran.bst']
bundle_files+=sorted((ROOT/'files').glob('*.tex'))+sorted((ROOT/'figures').glob('*'))
with zipfile.ZipFile(ROOT/'revised_source6.zip','w',compression=zipfile.ZIP_DEFLATED) as bundle:
    for path in bundle_files: bundle.write(path,path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(ROOT/'revised_source6.zip') as bundle:
    assert bundle.testzip() is None
    for path in bundle_files: assert bundle.read(path.relative_to(ROOT).as_posix())==path.read_bytes()
print('All numeric, math, citation, float, reference and heading checks passed.')
print('Wrote complete readable manuscript, 75-entry change record, and 13 location notes.')
