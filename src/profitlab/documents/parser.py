"""Deterministic visible HTML blocks and table coordinates; raw bytes stay separate."""
import hashlib
import re

from lxml import etree, html

from profitlab.contracts.sources import SourceBlock, TableCell

VERSION = 'html-2'


def normalize_quote(text):
    """Collapse Unicode whitespace, including NBSP; preserve case and punctuation."""
    return ' '.join(text.split())


def match_quote(text, quote):
    value = normalize_quote(quote)
    start = normalize_quote(text).find(value)
    return (start, start + len(value)) if value and start >= 0 else None


def parse_source(raw, filing_id):
    try:
        root = html.document_fromstring(raw)
    except etree.ParserError as error:
        raise ValueError('Source is not a readable HTML document') from error
    for node in root.xpath("//script|//style|//iframe|//form|//object|//embed|//*[local-name()='ix:hidden']"):
        node.drop_tree()
    for node in list(root.iter()):
        if isinstance(node.tag, str) and (node.get('hidden') is not None or
                re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', node.get('style', ''), re.IGNORECASE)):
            node.drop_tree()
    tree = root.getroottree()
    blocks, cells, tables = [], [], {}
    cell_positions = {}
    headings = []

    def identifier(prefix, locator):
        return prefix + '-' + hashlib.sha256(
            f'{filing_id}:{VERSION}:{locator}'.encode()).hexdigest()[:24]

    for node in root.xpath('//h1|//h2|//h3|//h4|//h5|//h6|//p|//table|//div[not(.//div or .//p or .//table or .//h1 or .//h2 or .//h3 or .//h4 or .//h5 or .//h6)]'):
        if node.xpath('ancestor::table'):
            continue
        locator = tree.getpath(node)
        text = node.text_content()
        if not normalize_quote(text):
            continue
        kind = 'table' if node.tag == 'table' else ('heading' if node.tag.startswith('h') else 'paragraph')
        if kind == 'heading':
            level = int(node.tag[1])
            headings = headings[:level - 1] + [normalize_quote(text)]
        table_id = identifier('table', locator) if kind == 'table' else None
        anchor_nodes = node.xpath('.//*[@id or @name]')
        original_anchor = node.get('id') or node.get('name')
        if not original_anchor and anchor_nodes:
            original_anchor = anchor_nodes[0].get('id') or anchor_nodes[0].get('name')
        block = SourceBlock(block_id=identifier('block', locator), filing_id=filing_id,
            dom_locator=locator, original_anchor=original_anchor,
            heading_path=list(headings), kind=kind, text=text, table_id=table_id,
            ordinal=len(blocks))
        blocks.append(block)
        if kind != 'table':
            continue
        occupied, rendered_rows, headers = {}, [], []
        for row_index, row in enumerate(node.xpath('.//tr[not(ancestor::table[2])]')):
            rendered, col = [], 0
            for element in row.xpath('./td|./th'):
                while (row_index, col) in occupied:
                    col += 1
                def span(name, element=element):
                    try:
                        return max(1, min(1000, int(element.get(name, '1'))))
                    except ValueError:
                        return 1
                rs, cs = span('rowspan'), span('colspan')
                if len(occupied) + rs * cs > 100000:
                    raise ValueError('Table span expansion limit exceeded')
                if row_index + rs > 10000 or col + cs > 10000:
                    raise ValueError('Table coordinate limit exceeded')
                cell = TableCell(cell_id=identifier('cell', tree.getpath(element)),
                    table_id=table_id, row_id=f'{table_id}-r{row_index}',
                    column_id=f'{table_id}-c{col}', raw_text=element.text_content(),
                    normalized_text=normalize_quote(element.text_content()),
                    row_span=rs, column_span=cs,
                    xbrl_fact_ids=[n.get('id') for n in element.iter() if n.get('id') and
                        isinstance(n.tag, str) and ('nonfraction' in n.tag.lower() or
                                                       'nonnumeric' in n.tag.lower())])
                for r in range(row_index, row_index + rs):
                    for c in range(col, col + cs):
                        if (r, c) in occupied:
                            raise ValueError('Overlapping table spans')
                        occupied[r, c] = cell.cell_id
                rendered.append({'cell_id': cell.cell_id, 'header': element.tag == 'th',
                                 'row': row_index, 'column': col})
                if element.tag == 'th':
                    headers.append((cell, row_index, col))
                cell_positions[cell.cell_id] = (len(cells), row_index, col)
                cells.append(cell)
                col += cs
            rendered_rows.append(rendered)
        table_cells = [c for c in cells if c.table_id == table_id]
        for cell in table_cells:
            index, r, c = cell_positions[cell.cell_id]
            related = [h for h, hr, hc in headers if h.cell_id != cell.cell_id and
                       ((hr <= r and hc <= c < hc + h.column_span) or hr == r)]
            replacement = cell.model_copy(update={
                'header_cell_ids': [h.cell_id for h in related],
                'year_cell_ids': [h.cell_id for h in related if re.search(r'\b(?:19|20)\d{2}\b', h.normalized_text)],
                'unit_cell_ids': [h.cell_id for h in related if re.search(r'USD|million|thousand|per.share', h.normalized_text, re.IGNORECASE)]})
            cells[index] = replacement
        tables[table_id] = {'caption': ' '.join(n.text_content() for n in node.xpath('./caption')),
                            'rows': rendered_rows}
    if not blocks:
        raise ValueError('HTML has no supported visible source blocks')
    return blocks, cells, tables
