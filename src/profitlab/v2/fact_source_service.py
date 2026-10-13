"""Inspection-only Inline XBRL mapping after Findings, using retained source bytes.

Supported numeric transforms are deliberately bounded. Unknown formats, malformed
contexts and source disagreement cannot produce a visible source claim.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from lxml import etree, html

from .canonical import (
    _canonicalize_root,
    _is_hidden,
    _line_nodes,
    _local_name,
    normalize_visible_text,
)
from .contracts import FactSourceLocation, FactSourceMapping, SourceRange

METHOD = 'inline-visible-1'
XBRLI = 'http://www.xbrl.org/2003/instance'
INLINE = {'http://www.xbrl.org/2008/inlineXBRL', 'http://www.xbrl.org/2013/inlineXBRL'}
TRANSFORMS = {
    'http://www.xbrl.org/inlineXBRL/transformation/2011-07-31': {'numdotdecimal', 'numcommadecimal', 'zerodash'},
    'http://www.xbrl.org/inlineXBRL/transformation/2015-02-26': {'numdotdecimal', 'numcommadecimal', 'zerodash'},
    'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12': {'num-dot-decimal', 'num-comma-decimal', 'fixed-zero'},
    'http://www.xbrl.org/inlineXBRL/transformation/2022-02-16': {'num-dot-decimal', 'num-comma-decimal', 'fixed-zero'},
}
MAX_OCCURRENCES = 100000
MAX_LOCATIONS = 1000
MAX_PROJECTION_BYTES = 4_000_000


def qname(node, value):
    """Resolve HTML-preserved namespace declarations, including local aliases."""
    if not value or ':' not in value:
        raise ValueError('Missing qualified namespace.')
    prefix, local = value.split(':', 1)
    for ancestor in (node, *node.iterancestors()):
        namespace = ancestor.get('xmlns:' + prefix.lower())
        if namespace:
            return namespace, local
    raise ValueError('Unresolved namespace.')


def element_is(node, namespace, local):
    try:
        uri, name = qname(node, node.tag)
        return uri == namespace and name.lower() == local
    except (ValueError, TypeError):
        return False


def context_matches(context, fact, cik):
    if not element_is(context, XBRLI, 'context'):
        return False
    fields = defaultdict(list)
    for node in context.iterdescendants():
        if _local_name(node.tag) in {'segment', 'scenario', 'explicitmember', 'typedmember'}:
            return False
        for name in ('identifier', 'startdate', 'enddate', 'instant'):
            if element_is(node, XBRLI, name):
                fields[name].append(node)
    if any(len(fields[name]) != 1 for name in ('identifier', 'startdate', 'enddate')) or fields['instant']:
        return False
    identifier = fields['identifier'][0]
    value = normalize_visible_text(identifier.text_content())
    if identifier.get('scheme') != 'http://www.sec.gov/CIK' or not value.isdigit() or int(value) != int(cik):
        return False
    return (date.fromisoformat(fields['startdate'][0].text_content()) == fact.period_start and
            date.fromisoformat(fields['enddate'][0].text_content()) == fact.period_end)


def unit_value(unit):
    if not element_is(unit, XBRLI, 'unit'):
        raise ValueError('Invalid unit element.')
    measures = [node for node in unit.iterdescendants() if element_is(node, XBRLI, 'measure')]
    tokens = []
    for node in measures:
        uri, name = qname(node, node.text_content().strip())
        if (uri, name) == ('http://www.xbrl.org/2003/iso4217', 'USD'):
            tokens.append('USD')
        elif (uri, name) == (XBRLI, 'shares'):
            tokens.append('shares')
        else:
            raise ValueError('Unsupported unit measure.')
    if len(tokens) == 1 and len(unit) == 1 and element_is(unit[0], XBRLI, 'measure'):
        return tokens[0]
    if tokens == ['USD', 'shares'] and len(unit) == 1 and element_is(unit[0], XBRLI, 'divide'):
        divide = unit[0]
        if (len(divide) == 2 and element_is(divide[0], XBRLI, 'unitnumerator') and
                element_is(divide[1], XBRLI, 'unitdenominator') and
                all(len(child) == 1 and element_is(child[0], XBRLI, 'measure') for child in divide)):
            return 'USD/shares'
    raise ValueError('Unsupported unit structure.')


def numeric_value(node):
    # continuedAt is defined for nonNumeric, not nonFraction. Never concatenate
    # arbitrary continuation text into a numeric cell.
    if node.get('continuedat') or node.get('target') or node.get('xsi:nil') == 'true':
        raise ValueError('Unsupported numeric continuation, target, or nil fact.')
    if any(_local_name(child.tag) in {'exclude', 'nonfraction', 'fraction', 'hidden', 'header', 'references',
                                               'script', 'style', 'iframe', 'form', 'object', 'embed'} or _is_hidden(child)
           for child in node.iterdescendants()):
        raise ValueError('Unsupported excluded, nested, or hidden numeric content.')
    text = normalize_visible_text(node.text_content())
    if not text or len(text) > 1000:
        raise ValueError('Numeric display text exceeds bounds or is empty.')
    fmt = node.get('format')
    namespace = None
    token = text
    if fmt:
        namespace, name = qname(node, fmt)
        if name not in TRANSFORMS.get(namespace, set()):
            raise ValueError('Unsupported numeric transformation.')
        if name in {'fixed-zero', 'zerodash'}:
            if name == 'zerodash' and text not in {'-', '–', '—'}:
                raise ValueError('Invalid zero-dash display.')
            token = '0'
        else:
            comma_decimal = name in {'num-comma-decimal', 'numcommadecimal'}
            compact = text.replace(' ', '')
            pattern = r'[0-9]+(?:\.[0-9]+)*(?:,[0-9]+)?' if comma_decimal else r'[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?'
            if not re.fullmatch(pattern, compact):
                raise ValueError('Invalid transformed numeric text.')
            token = compact.replace('.', '').replace(',', '.') if comma_decimal else compact.replace(',', '')
    elif not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', token):
        raise ValueError('Invalid unformatted decimal.')
    sign = node.get('sign', '')
    scale = int(node.get('scale', '0'))
    if sign not in {'', '-'} or not -100 <= scale <= 100:
        raise ValueError('Unsupported sign or scale.')
    displayed = Decimal(token)
    with localcontext() as ctx:
        ctx.prec = len(displayed.as_tuple().digits) + abs(scale) + 2
        transformed = displayed * (Decimal(10) ** scale) * (-1 if sign == '-' else 1)
    return {'display_text': text, 'format': fmt, 'format_namespace': namespace,
            'sign': sign, 'scale': scale, 'displayed_value': displayed,
            'transformed_value': transformed}


class FactSourceService:
    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository

    def enrich(self, run, facts, presentations=()):
        if self.repo.stage(run.run_id, 'findings').status != 'completed':
            raise ValueError('Findings must be sealed before fact source mapping begins.')
        filing = self.repo.filing(run.run_id)
        try:
            document_id = filing['document_id']
            document = self.repo.canonical_document(run.run_id, document_id)
            raw = self.repo.raw_html(run.run_id, document_id)
            visible = self.repo.visible_html(run.run_id, document_id)
            result = self.map(raw, document, visible, filing, facts, presentations)
        except (KeyError, FileNotFoundError, ValueError, etree.ParserError) as error:
            refs = {item.fact_id: item.locations for item in presentations}
            result = [FactSourceMapping(fact_id=f.fact_id, status='unavailable',
                      presentation_references=refs.get(f.fact_id, []),
                      diagnostics=[f'Retained primary source unavailable or inconsistent: {error}']) for f in facts]
        self.repo.save_fact_source_mappings(run.run_id, result)
        return result

    @staticmethod
    def map(raw, document, visible, filing, facts, presentations=()):
        if len(raw) > 50_000_000 or hashlib.sha256(raw).hexdigest() != document.ref.source_hash:
            raise ValueError('Retained raw source hash mismatch or source size limit.')
        if document.ref.filing_id != filing['filing_id'] or filing.get('source_hash', document.ref.source_hash) != document.ref.source_hash:
            raise ValueError('Retained filing identity/hash disagrees with canonical source.')
        root = html.document_fromstring(raw)
        tree = root.getroottree()
        ids = defaultdict(list)
        occurrences = []
        line_nodes = {node for node, _ in _line_nodes(root)}
        for node in root.iter():
            if node.get('id'):
                ids[node.get('id')].append(node)
            if _local_name(node.tag) == 'nonfraction':
                occurrences.append(node)
        if len(occurrences) > MAX_OCCURRENCES:
            raise ValueError('Inline occurrence scan limit reached.')
        candidates = defaultdict(list)
        rejected = defaultdict(Counter)
        hidden = Counter()
        for node in occurrences:
            try:
                ix_uri, _ = qname(node, node.tag)
                if ix_uri not in INLINE:
                    continue
                concept_uri, tag = qname(node, node.get('name'))
            except ValueError:
                continue
            for fact in facts:
                namespace, concept = fact.concept.split(':', 1)
                if tag != concept or namespace != 'us-gaap' or not re.fullmatch(r'https?://fasb.org/us-gaap/\d{4}', concept_uri):
                    continue
                try:
                    if fact.accession != filing['accession'] or fact.form != filing['form']:
                        raise ValueError('Fact filing identity differs from retained filing.')
                    contexts, units = ids[node.get('contextref')], ids[node.get('unitref')]
                    if len(contexts) != 1 or len(units) != 1:
                        raise ValueError('Context/unit reference is missing or duplicated.')
                    if not context_matches(contexts[0], fact, filing['cik']) or unit_value(units[0]) != fact.unit:
                        continue
                    numeric = numeric_value(node)
                    if numeric['transformed_value'] != fact.value:
                        continue
                    ancestors = list(node.iterancestors())
                    if any(_local_name(a.tag) in {'hidden', 'header', 'references', 'script', 'style', 'iframe', 'form', 'object', 'embed'} or _is_hidden(a) for a in (node, *ancestors)):
                        hidden[fact.fact_id] += 1
                        continue
                    owner = next((a for a in ancestors if a in line_nodes), None)
                    cell = next((a for a in ancestors if _local_name(a.tag) in {'td', 'th'}), owner)
                    if owner is None or cell is None:
                        raise ValueError('Visible occurrence has no canonical line owner.')
                    candidates[fact.fact_id].append({
                        'owner': owner, 'cell': cell, 'raw_dom_reference': tree.getpath(node),
                        'inline_id': node.get('id'), 'concept_namespace': concept_uri,
                        'context_id': node.get('contextref'), 'entity_identifier': str(filing['cik']),
                        'period_start': fact.period_start, 'period_end': fact.period_end,
                        'unit': fact.unit, **numeric,
                    })
                except (ValueError, InvalidOperation) as error:
                    rejected[fact.fact_id][str(error)] += 1
        rebuilt, rebuilt_visible = _canonicalize_root(root, raw, document_id=document.ref.document_id,
                                                      filing_id=document.ref.filing_id)
        if rebuilt != document or rebuilt_visible != visible:
            raise ValueError('Retained canonical lines or sanitized HTML disagree with raw source.')
        lines = {line.dom_reference: line for line in document.lines}
        presentation_by_id = {item.fact_id: item for item in presentations}
        result = []
        for fact in facts:
            locations = []
            projected_bytes = 0
            for candidate in candidates[fact.fact_id]:
                owner, cell = candidate.pop('owner'), candidate.pop('cell')
                line = lines.get(tree.getpath(owner))
                cell_text = normalize_visible_text(cell.text_content())
                if line is None or candidate['display_text'] not in cell_text or cell_text not in line.text:
                    rejected[fact.fact_id]['Visible numeric cell disagrees with canonical row.'] += 1
                    continue
                headers = []
                table = next((a for a in owner.iterancestors() if _local_name(a.tag) == 'table'), None)
                if table is not None:
                    # Retain nearby preceding rows (period/scale headings) as visible
                    # context only. Exact semantic period/unit come from the context.
                    rows = [row for row in table.xpath('.//tr') if tree.getpath(row) in lines]
                    index = rows.index(owner) if owner in rows else 0
                    context_rows = list(dict.fromkeys(rows[:min(4, index)] + rows[max(0, index - 4):index]))
                    first_line = next((lines.get(tree.getpath(row)) for row in rows
                                       if lines.get(tree.getpath(row))), None)
                    if first_line:
                        headers.extend(line.text for line in document.lines[max(0, first_line.line_number - 5):first_line.line_number - 1]
                                       if len(line.text) <= 2000)
                    for row in context_rows:
                        header = lines.get(tree.getpath(row))
                        if header and len(header.text) <= 2000:
                            headers.append(header.text)
                try:
                    location = FactSourceLocation(fact_id=fact.fact_id,
                        source_range=SourceRange(document_id=document.ref.document_id,
                            source_hash=document.ref.source_hash, start_line=line.line_number, end_line=line.line_number),
                        html_anchor=line.html_anchor, quote=line.text,
                        cell_dom_reference=tree.getpath(cell), cell_text=cell_text,
                        header_context=headers, **candidate)
                    projected_bytes += len(location.model_dump_json().encode())
                    if len(locations) >= MAX_LOCATIONS or projected_bytes > MAX_PROJECTION_BYTES:
                        raise ValueError('Fact source projection limit reached; no partial index claimed.')
                    locations.append(location)
                except ValueError as error:
                    rejected[fact.fact_id][str(error)] += 1
                    locations = []
                    break
            diagnostics = [f'{count} occurrence(s): {reason}' for reason, count in rejected[fact.fact_id].most_common(18)]
            status = ('ambiguous' if rejected[fact.fact_id] else 'verified' if locations else
                      'hidden_only' if hidden[fact.fact_id] else 'unavailable')
            diagnostics.append(f'{len(locations)} verified visible occurrence(s); {hidden[fact.fact_id]} exact hidden occurrence(s).')
            if not locations:
                diagnostics.append('No verified canonical source link. Separate SEC reports and PRE rows do not establish a primary-filing line.')
            presentation = presentation_by_id.get(fact.fact_id)
            result.append(FactSourceMapping(fact_id=fact.fact_id, status=status,
                document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                locations=locations, diagnostics=diagnostics,
                presentation_references=presentation.locations if presentation else []))
        if len(json.dumps([item.model_dump(mode='json') for item in result]).encode()) > MAX_PROJECTION_BYTES:
            raise ValueError('Run fact source projection byte limit reached.')
        return result
