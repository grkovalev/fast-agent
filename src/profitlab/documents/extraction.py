"""Conservative visible-table extraction; unsupported layouts stay diagnostic."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import html

from profitlab.contracts.base import FiscalPeriod
from profitlab.contracts.facts import Metric

CONCEPTS = {
    'us-gaap:EarningsPerShareDiluted': Metric.EPS_DILUTED,
    'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding': Metric.SHARES_DILUTED,
    'us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic': Metric.NET_INCOME_COMMON,
    'us-gaap:NetIncomeLoss': Metric.NET_INCOME_CONSOLIDATED,
    'us-gaap:ProfitLoss': Metric.NET_INCOME_CONSOLIDATED,
}


def number(raw):
    text = raw.strip().replace('\u2212', '-').replace('\xa0', '').replace(' ', '')
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if ',' in text and not re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?', text):
        raise ValueError('Unsupported comma grouping/decimal transformation')
    text = text.replace(',', '')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
        raise ValueError('Unsupported numeric text; missingness is not zero.')
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError('Invalid decimal') from None


def metric_for(label):
    text = label.lower()
    if 'diluted' in text and ('per share' in text or 'eps' in text):
        return Metric.EPS_DILUTED
    if 'diluted' in text and ('shares' in text or 'share count' in text):
        return Metric.SHARES_DILUTED
    if 'net income' in text or 'earnings attributable' in text:
        if 'common' in text:
            return Metric.NET_INCOME_COMMON
        if 'parent' in text:
            return Metric.NET_INCOME_PARENT
        return Metric.NET_INCOME_CONSOLIDATED
    return None


def table_figures(doc, retained):
    figures, issues = {}, []
    blocks = {b.block_id: b for b in doc['blocks']}
    cells = doc['cells']
    # Exact intervals are mandatory; don't synthesize January starts for fiscal calendars.
    period_text = '\n'.join(b.text for b in doc['blocks'] if b.kind != 'table')
    periods = re.findall(r'(\d{4}-\d{2}-\d{2})\s+(?:through|to)\s+(\d{4}-\d{2}-\d{2})', period_text)
    for block in blocks.values():
        if block.block_id not in retained or block.kind != 'table':
            continue
        table = doc['index']['tables'][block.table_id]
        context = ' '.join(block.heading_path) + ' ' + table['caption']
        first_column_units = ' '.join(cells[c['cell_id']].normalized_text
            for row in table['rows'][:1] for c in row if c['header'] and c['column'] == 0)
        for row in table['rows']:
            row_cells = [cells[c['cell_id']] for c in row]
            if not row_cells:
                continue
            label = row_cells[0].normalized_text
            metric = metric_for(label)
            if metric is None:
                # Some supported notes put the metric/unit in the first column header.
                metric = metric_for(' '.join(cells[h].normalized_text for c in row_cells
                                            for h in c.header_cell_ids if h in cells))
            if metric is None:
                continue
            if 'basic' in label.lower() and 'diluted' not in label.lower() and metric in (Metric.EPS_DILUTED, Metric.SHARES_DILUTED):
                continue
            row_context = context + ' ' + label
            for coordinate, cell in zip(row[1:], row_cells[1:]):
                if coordinate['header']:
                    continue
                try:
                    value = number(cell.raw_text)
                except ValueError:
                    continue
                year_headers = [cells[h].normalized_text for h in cell.year_cell_ids]
                years = set(re.findall(r'\b(?:19|20)\d{2}\b', ' '.join(year_headers)))
                if value in {Decimal(y) for y in years}:
                    continue
                reasons = []
                if len(years) != 1:
                    reasons.append('Missing or ambiguous year column')
                year = int(next(iter(years))) if len(years) == 1 else None
                exact = [(s, e) for s, e in periods if date.fromisoformat(e).year == year]
                if len(set(exact)) != 1:
                    reasons.append('Exact fiscal interval unavailable; no calendar-year inference')
                lower = row_context.lower()
                if re.search(r'quarter|three months|six months|nine months|ytd', lower):
                    reasons.append('Quarterly/YTD presentation')
                accounting_context = re.sub(r'\bsplit[- ]adjusted\b', '', lower)
                if re.search(r'adjusted|non-gaap', accounting_context):
                    reasons.append('Adjusted accounting basis')
                if re.search(r'\bsegment\b', lower):
                    reasons.append('Segment scope')
                if not re.search(r'annual|year[s]? ended|income statement|operations', lower):
                    reasons.append('Annuality not explicit')
                units = row_context + ' ' + first_column_units + ' ' + ' '.join(cells[h].normalized_text for h in cell.unit_cell_ids)
                if metric != Metric.SHARES_DILUTED and not re.search(r'USD|US dollars|\$', units):
                    reasons.append('Currency context unavailable')
                scale = Decimal(1)
                if metric != Metric.EPS_DILUTED:
                    scale_context = label if re.search(r'million|thousand', label, re.IGNORECASE) else first_column_units if re.search(r'million|thousand', first_column_units, re.IGNORECASE) else units
                    if 'million' in scale_context.lower():
                        scale = Decimal(1000000)
                    elif 'thousand' in scale_context.lower():
                        scale = Decimal(1000)
                    elif not re.search(r'USD|shares|dollars', units, re.IGNORECASE):
                        reasons.append('Unit context unavailable')
                elif not re.search(r'per.share|EPS', label, re.IGNORECASE):
                    reasons.append('Per-share context unavailable')
                entry = {'block_id': block.block_id, 'cell_id': cell.cell_id, 'metric': metric,
                    'raw_numeric_text': cell.raw_text, 'value': str(value * scale), 'scale': str(scale),
                    'raw_label': label, 'reasons': reasons}
                if exact:
                    s, e = exact[0]
                    entry['period'] = FiscalPeriod(start=s, end=e, fiscal_year=year).model_dump(mode='json')
                if reasons:
                    issues.append(entry)
                else:
                    figures[cell.cell_id] = entry
    return figures, issues


def inline_figures(raw, doc, retained):
    """Only visible, cell-anchored duration facts with simple decimal transforms."""
    root = html.document_fromstring(raw)
    contexts = {n.get('id'): n for n in root.iter() if isinstance(n.tag, str)
                and n.tag.lower().split(':')[-1] == 'context'}
    units = {n.get('id'): n.text_content().strip() for n in root.iter()
             if isinstance(n.tag, str) and n.tag.lower().split(':')[-1] == 'unit'}
    blocks = {b.table_id: b for b in doc['blocks'] if b.table_id}
    mapped = {fid: c for c in doc['cells'].values() for fid in c.xbrl_fact_ids}
    figures, issues = {}, []
    for node in root.iter():
        if not isinstance(node.tag, str) or node.tag.lower().split(':')[-1] != 'nonfraction':
            continue
        concept = node.get('name')
        cell = mapped.get(node.get('id'))
        if concept not in CONCEPTS:
            if cell is not None and blocks[cell.table_id].block_id in retained:
                issues.append({'fact_id': node.get('id'), 'reasons': ['Unsupported taxonomy concept']})
            continue
        if cell is None or blocks[cell.table_id].block_id not in retained:
            issues.append({'fact_id': node.get('id'), 'reasons': ['Hidden-only or unretained XBRL fact']})
            continue
        context = contexts.get(node.get('contextref'))
        try:
            if any('hidden' in str(n.tag).lower() or n.get('hidden') is not None or
                   re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', n.get('style', ''), re.IGNORECASE)
                   for n in [node, *node.iterancestors()]):
                raise ValueError('Hidden-only XBRL fact')
            block = blocks[cell.table_id]
            row_labels = ' '.join(doc['cells'][c['cell_id']].normalized_text
                for row in doc['index']['tables'][cell.table_id]['rows'] for c in row
                if doc['cells'][c['cell_id']].row_id == cell.row_id)
            visible_context = (' '.join(block.heading_path) + ' ' + row_labels).lower()
            accounting_context = re.sub(r'\bsplit[- ]adjusted\b', '', visible_context)
            if re.search(r'adjusted|non-gaap|\bsegment\b', accounting_context):
                raise ValueError('Adjusted or segment XBRL presentation')
            if context is None:
                raise ValueError('Missing XBRL context')
            if any('member' in n.tag.lower() or 'segment' in n.tag.lower() for n in context.iter()):
                raise ValueError('Unsupported dimensional/segment context')
            dates = {n.tag.lower().split(':')[-1]: n.text_content().strip() for n in context.iter()}
            start, end = date.fromisoformat(dates['startdate']), date.fromisoformat(dates['enddate'])
            year_labels = ' '.join(doc['cells'][h].normalized_text for h in cell.year_cell_ids)
            header_years = set(re.findall(r'\b(?:19|20)\d{2}\b', year_labels))
            if header_years and header_years != {str(end.year)}:
                raise ValueError('XBRL context conflicts with visible year column')
            if not 330 <= (end - start).days <= 380:
                raise ValueError('Nonannual XBRL duration')
            if node.get('format', '').split(':')[-1] not in ('', 'num-dot-decimal'):
                raise ValueError('Unsupported XBRL transformation')
            if node.get('sign', '') not in ('', '-'):
                raise ValueError('Unsupported XBRL sign')
            unit = units.get(node.get('unitref'), '')
            metric = CONCEPTS[concept]
            if (metric == Metric.EPS_DILUTED and not ('USD' in unit and 'shares' in unit)
                or metric == Metric.SHARES_DILUTED and unit.split(':')[-1] != 'shares'
                or metric not in (Metric.EPS_DILUTED, Metric.SHARES_DILUTED) and unit.split(':')[-1] != 'USD'):
                raise ValueError('Missing or unsupported XBRL unit')
            exponent = int(node.get('scale', '0'))
            if abs(exponent) > 12:
                raise ValueError('Unsupported XBRL scale')
            scale = Decimal(10) ** exponent
            value = number(node.text_content()) * scale
            if node.get('sign') == '-':
                value = -abs(value)
            if node.text_content().strip() != cell.raw_text.strip():
                raise ValueError('Visible cell does not exactly represent XBRL fact')
            figures[cell.cell_id] = {'block_id': blocks[cell.table_id].block_id,
                'cell_id': cell.cell_id, 'metric': metric, 'raw_numeric_text': cell.raw_text,
                'value': str(value), 'scale': str(scale), 'raw_label': concept,
                'period': FiscalPeriod(start=start, end=end, fiscal_year=end.year).model_dump(mode='json'),
                'reasons': []}
        except (ValueError, KeyError) as error:
            issues.append({'fact_id': node.get('id'), 'cell_id': cell.cell_id, 'reasons': [str(error)]})
    return figures, issues


def validate_figure(proposal, chunk, doc, supported):
    """Validate untrusted citations before constructing any FactCandidate."""
    raw = proposal.model_dump(mode='json')
    if proposal.block_id not in chunk.block_ids or proposal.cell_id not in chunk.cell_ids:
        return 'rejected', ['Unknown or out-of-chunk source identity'], None
    cell = doc['cells'][proposal.cell_id]
    block = next((b for b in doc['blocks'] if b.block_id == proposal.block_id), None)
    if block is None or block.table_id != cell.table_id:
        return 'rejected', ['Cell belongs to a different source block/table'], None
    if proposal.raw_numeric_text != cell.raw_text:
        return 'rejected', ['Raw numeric text does not match cited cell'], None
    years = set(re.findall(r'\b(?:19|20)\d{2}\b',
        ' '.join(doc['cells'][h].normalized_text for h in cell.year_cell_ids)))
    if years and years != {str(proposal.period.fiscal_year)}:
        return 'rejected', ['Wrong-year source column'], None
    entry = supported.get(proposal.cell_id)
    if not entry:
        return 'ambiguous', ['Source context cannot mechanically validate metric/year/unit; unavailable for selection'], None
    if (any(str(raw[k]) != str(entry[k]) for k in ('block_id', 'metric', 'raw_numeric_text', 'period'))
        or Decimal(raw['value']) != Decimal(entry['value']) or Decimal(raw['scale']) != Decimal(entry['scale'])):
        return 'rejected', ['Source value, metric, scale or fiscal interval mismatch'], None
    return 'accepted', ['Exact source and normalized value matched'], entry
