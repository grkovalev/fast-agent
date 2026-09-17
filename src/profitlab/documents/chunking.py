"""Block coverage and row-preserving chunks. Estimates are a proxy, not Jev usage."""
import hashlib
import json
import math

from profitlab.contracts.sources import Chunk

VERSION = 'blocks-1'
ESTIMATOR = 'utf8-bytes-div3-ceil-1'


def estimate(text):
    return math.ceil(len(text.encode('utf-8')) / 3)


def chunk_document(filing, blocks, cells, tables, settings):
    if settings.chunk_overlap_tokens >= settings.chunk_target_tokens:
        raise ValueError('Chunk overlap must be smaller than target.')
    chunks, pending, overlap = [], [], []
    metadata = f'Filing {filing.filing_id}; {filing.form}; report {filing.report_date}; filed {filing.filing_date}'

    def text_for(primary, context, body=None):
        heading = ' / '.join(primary[0].heading_path)
        return metadata + '\nSection: ' + heading + '\n' + '\n'.join(
            b.text for b in context) + '\n' + (body if body is not None else '\n'.join(
                b.text for b in primary))

    def fits(text):
        return estimate(text) + settings.chunk_question_overhead <= settings.chunk_request_budget

    def emit(primary, context=(), body=None, table_id=None, selected=(), primary_cells=(), piece=1):
        text = text_for(primary, context, body)
        if not fits(text):
            raise ValueError(f'Oversized unsupported block/row: {primary[0].block_id}; no truncation performed')
        refs = list(dict.fromkeys(b.block_id for b in [*context, *primary]))
        digest = hashlib.sha256(text.encode()).hexdigest()
        identity = json.dumps([VERSION, refs, list(primary_cells), digest,
                              settings.chunk_target_tokens, settings.chunk_overlap_tokens,
                              settings.chunk_request_budget, settings.chunk_question_overhead])
        chunks.append(Chunk(chunk_id='chunk-' + hashlib.sha256(identity.encode()).hexdigest()[:24],
            filing_id=filing.filing_id, block_ids=refs,
            primary_block_ids=[b.block_id for b in primary],
            overlap_block_ids=[b.block_id for b in context] if table_id is None else [],
            context_block_ids=[b.block_id for b in context] if table_id else [],
            text=text, token_estimate=estimate(text), estimator_version=ESTIMATOR,
            request_token_estimate=estimate(text) + settings.chunk_question_overhead,
            source_anchors=['#block-' + b for b in refs], content_hash=digest,
            heading_path=primary[0].heading_path, cell_ids=list(selected),
            primary_cell_ids=list(primary_cells), table_id=table_id, piece=piece))
        if len(chunks) > settings.chunk_max_count:
            raise ValueError('Chunk count limit exceeded; evidence is incomplete.')

    def flush():
        nonlocal pending, overlap
        if not pending:
            return
        emit(pending, overlap)
        overlap = []
        for b in reversed(pending):
            if b.kind == 'heading' or estimate(b.text) + sum(estimate(x.text) for x in overlap) > settings.chunk_overlap_tokens:
                break
            overlap.insert(0, b)
        pending = []

    for pos, block in enumerate(blocks):
        if block.filing_id != filing.filing_id:
            raise ValueError('Cross-filing source block')
        if block.kind != 'table':
            if pending and (block.heading_path != pending[0].heading_path or
                    estimate(text_for([*pending, block], overlap)) > settings.chunk_target_tokens or
                    not fits(text_for([*pending, block], overlap))):
                flush()
            if block.kind == 'heading':
                overlap = []
            if not fits(text_for([block], overlap)):
                overlap = []
            pending.append(block)
            continue
        flush()
        overlap = []
        # Immediate prose/caption/notes accompany every table piece; never overlap tables.
        context = [b for b in blocks[max(0, pos-1):pos] + blocks[pos+1:pos+2]
                   if b.kind != 'table' and b.heading_path == block.heading_path]
        table = tables[block.table_id]
        rows = table['rows']
        all_ids = [c['cell_id'] for row in rows for c in row]
        if fits(text_for([block], context)):
            emit([block], context, table_id=block.table_id, selected=all_ids, primary_cells=all_ids)
            continue
        # Repeat all header, year and unit rows, plus all rows before the first header.
        header_rows = set()
        for i, row in enumerate(rows):
            if row and all(c['header'] for c in row):
                header_rows.add(i)
            else:
                break
        referenced = {h for cid in all_ids for h in
                      cells[cid].year_cell_ids + cells[cid].unit_cell_ids}
        header_rows.update(i for i, row in enumerate(rows) if row and
                           all(c['header'] or c['cell_id'] in referenced for c in row))
        if header_rows:
            header_rows.update(range(min(header_rows)))
        else:
            raise ValueError(f'Oversized table has no supported headers: {block.table_id}')
        headers = [rows[i] for i in sorted(header_rows)]
        data = [(i, row) for i, row in enumerate(rows) if i not in header_rows]
        if not data:
            raise ValueError(f'Oversized unsupported row/header group: {block.table_id}')

        def render(group, table=table, headers=headers):
            return table['caption'] + '\n' + '\n'.join(' | '.join(
                cells[c['cell_id']].raw_text for c in row) for row in [*headers, *group])

        # Keep rows connected by rowspans together; splitting their labels is unsafe.
        groups, group, end = [], [], -1
        for i, row in data:
            if group and i >= end:
                groups.append(group)
                group = []
            group.append(row)
            end = max(end, i+1, *(i + cells[c['cell_id']].row_span for c in row))
        if group:
            groups.append(group)
        batch, piece = [], 1
        for group in groups:
            if batch and not fits(text_for([block], context, render([*batch, *group]))):
                ids = [c['cell_id'] for row in [*headers, *batch] for c in row]
                emit([block], context, render(batch), block.table_id, ids,
                     [c['cell_id'] for row in batch for c in row], piece)
                piece += 1
                batch = []
            if not fits(text_for([block], context, render(group))):
                raise ValueError(f'Oversized unsupported row group: {block.table_id}; no truncation performed')
            batch.extend(group)
        if batch:
            emit([block], context, render(batch), block.table_id,
                 [c['cell_id'] for row in [*headers, *batch] for c in row],
                 [c['cell_id'] for row in batch for c in row], piece)
    flush()
    return chunks
