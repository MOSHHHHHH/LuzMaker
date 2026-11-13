"""Independent MuPDF check: physical bounds, fonts, all departures, RTL glyph order."""
import collections
import json
import re
import sys
import fitz

manifest=json.load(open(sys.argv[1]))
for fixture in manifest:
    doc=fitz.open(fixture['file'])
    if fixture.get('pages'):assert len(doc)==fixture['pages'],fixture['name']
    actual=[];part_pages=collections.defaultdict(list);ordered_long=[]
    for page_number,page in enumerate(doc):
        assert abs(page.rect.width-595.28)<.1 and abs(page.rect.height-841.89)<.1
        assert all(font[1] not in ('n/a','') for font in page.get_fonts()),'Fonts must be embedded'
        # Content is vector text, not a screenshot of the page.
        text=page.get_text('text');assert text.strip()
        chars=[]
        for block in page.get_text('rawdict')['blocks']:
            if block['type']!=0:continue
            x0,y0,x1,y1=block['bbox']
            assert 27<=x0<=x1<=page.rect.width-27,(fixture['name'],page_number,block['bbox'])
            assert 24<=y0<=y1<=page.rect.height-24,(fixture['name'],page_number,block['bbox'])
            for line in block['lines']:
                line_chars=[c for span in line['spans'] for c in span['chars']]
                chars.extend(line_chars)
                visual=''.join(c['c'] for c in sorted(line_chars,key=lambda c:c['bbox'][0]))
                if fixture['name']=='continuations':
                    for title,expected in [('לוח ראשון','ןושאר חול'),('לוח שני','ינש חול')]:
                        if expected in visual:
                            match=re.search(r'ךותמ\s+(\d+)\s+קלח',visual);assert match,repr(visual)
                            part_pages[title].append((int(match[1]),page_number))
                if fixture['name']=='mixed' and 'A4' in visual:
                    assert visual=='13.11.2026 — ז״פשת ןוושחב ג״י — (A4) א15 וק',repr(visual)
        # Each departure is a separately drawn LTR clock in the table body.
        for word in page.get_text('words'):
            if re.fullmatch(r'\d{2}:\d{2}',word[4]):actual.append(word[4])
        if fixture['name']=='long':
            clocks=[w for w in page.get_text('words') if re.fullmatch(r'\d{2}:\d{2}',w[4])]
            ordered_long.extend(w[4] for w in sorted(clocks,key=lambda w:(-round(w[0],1),w[1])))
        assert '03:00–02:59' in text,'Numeric time range must retain LTR order inside the RTL footer'
        assert 'רקיימ' in text or 'מייקר' in text,'Hebrew glyphs must survive ToUnicode mapping'
        if fixture['name']=='mixed':
            # Compare physical glyph sequence against standard Unicode BiDi's
            # expected visual order for the mixed Hebrew/Latin heading.
            assert 'A4' in text and '13.11.2026' in text
            assert any('15' in line for line in text.splitlines())
    if fixture['name']=='long':assert ordered_long==fixture['rows'],'Read down each column, right to left, then continue on the next page'
    if fixture['name']=='continuations':assert set(part_pages)=={'לוח ראשון','לוח שני'}
    for title,parts in part_pages.items():assert [part for part,_ in parts]==[1,2],(title,parts)
    assert collections.Counter(actual)==collections.Counter(fixture['rows']),(fixture['name'],len(actual),len(fixture['rows']))
    print('PASS: independent PDF bounds, embedded fonts and lossless departures:',fixture['name'])
