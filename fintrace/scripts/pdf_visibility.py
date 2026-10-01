"""Source-geometry correction for invisible accounting alignment brackets.

No financial values or answer keys are embedded here. A correction requires
an unmatched closing bracket in a numeric cell AND a matching PDF glyph whose
light foreground colour matches its local filled rectangle (or white page).
Raw model output is kept separately. Other malformed numbers are not repaired.
"""
import copy
import re


def grey(colour):
    if isinstance(colour,(int,float)):
        return float(colour)
    if isinstance(colour,(list,tuple)):
        if len(colour)==1:
            return float(colour[0])
        if len(colour)==3 and max(colour)-min(colour)<0.01:
            return float(colour[0])
    return None


def hidden_bracket(char, rectangles):
    foreground=grey(char.get('non_stroking_color'))
    if char.get('text')!=')' or foreground is None or foreground<0.9:
        return False
    x=(char['x0']+char['x1'])/2
    y=(char['top']+char['bottom'])/2
    backgrounds=[r for r in rectangles if r.get('fill') and r['x0']<=x<=r['x1'] and r['top']<=y<=r['bottom']]
    if backgrounds:
        # The smallest containing filled rectangle is the local cell/text fill.
        background=grey(min(backgrounds,key=lambda r:(r['x1']-r['x0'])*(r['bottom']-r['top']))['non_stroking_color'])
    else:
        background=1.0
    return background is not None and abs(foreground-background)<0.01


def correct_tables(document, page):
    doc=copy.deepcopy(document)
    corrections=[]
    unresolved=[]
    for ti,table in enumerate(doc.get('tables',[])):
        for ci,cell in enumerate(table['data']['table_cells']):
            text=cell['text'].strip()
            if not re.fullmatch(r'[+\-]?\d[\d,]*(?:\.\d+)?\)',text):
                continue
            box=cell.get('bbox')
            reason={'table_index':ti,'cell_index':ci,'raw_text':cell['text']}
            if box and box['coord_origin']=='TOPLEFT':
                candidates=[c for c in page.chars if c['text']==')'
                    and box['l']-2 <= (c['x0']+c['x1'])/2 <= box['r']+2
                    and box['t']-2 <= (c['top']+c['bottom'])/2 <= box['b']+2]
                if len(candidates)==1 and hidden_bracket(candidates[0],page.rects):
                    char=candidates[0]
                    cell['raw_text']=cell['text']
                    cell['text']=text[:-1]
                    change={**reason,'corrected_text':cell['text'],
                        'method':'source_confirmed_background_colour_bracket',
                        'glyph_bbox':[char['x0'],char['top'],char['x1'],char['bottom']],
                        'glyph_colour':char['non_stroking_color']}
                    cell['extraction_correction']=change
                    corrections.append(change)
                    continue
            unresolved.append(reason)
    return doc,corrections,unresolved
