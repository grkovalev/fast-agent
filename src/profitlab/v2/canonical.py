"""Visible, line-addressable filing source for the V2 pipeline.

The canonical representation deliberately contains no Inline XBRL semantics.  It is
the only source-text API used by later V2 stages: persisted lines are normalized
visible text, while the separately persisted sanitized HTML provides a human
inspectable anchor target for each line.
"""
import hashlib
import re
from collections.abc import Iterable

from lxml import etree, html
from pydantic import Field

from .contracts import CanonicalDocumentRef, SourceRange, V2Contract

CANONICAL_VERSION = 'visible-html-1'
_XBRL_ATTRIBUTES = {
    'contextref', 'unitref', 'decimals', 'scale', 'format', 'sign', 'continuedat',
    'escape', 'footnoteid', 'id', 'name', 'target', 'tupleid', 'order', 'precision',
}


def normalize_visible_text(value: str) -> str:
    """The documented whitespace policy: Unicode whitespace becomes one space."""
    return ' '.join(value.split())


def _local_name(value) -> str:
    if not isinstance(value, str):
        return ''
    return value.rsplit('}', 1)[-1].rsplit(':', 1)[-1].lower()


def _is_hidden(node) -> bool:
    style = node.get('style', '')
    return (node.get('hidden') is not None or node.get('aria-hidden') == 'true' or
            bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', style,
                           re.IGNORECASE)))


class CanonicalLine(V2Contract):
    line_number: int = Field(ge=1)
    text: str = Field(min_length=1)
    element_type: str = Field(pattern=r'^(heading|paragraph|list_item|caption|table_row)$')
    html_anchor: str = Field(min_length=1)
    dom_reference: str = Field(min_length=1)


class CanonicalDocument(V2Contract):
    ref: CanonicalDocumentRef
    lines: list[CanonicalLine]

    def __init__(self, **data):
        super().__init__(**data)
        if len(self.lines) != self.ref.line_count:
            raise ValueError('Canonical line count does not match its document reference')
        if [line.line_number for line in self.lines] != list(range(1, len(self.lines) + 1)):
            raise ValueError('Canonical lines must be contiguous and ordered')

    def _validate_range(self, source_range: SourceRange) -> None:
        if (source_range.document_id != self.ref.document_id or
                source_range.source_hash != self.ref.source_hash):
            raise ValueError('Source range does not belong to this canonical document')
        if source_range.end_line > self.ref.line_count:
            raise ValueError('Source range exceeds canonical document')

    def slice(self, source_range: SourceRange) -> str:
        self._validate_range(source_range)
        selected = self.lines[source_range.start_line - 1:source_range.end_line]
        text = '\n'.join(line.text for line in selected)
        if source_range.start_character is not None:
            if source_range.start_line != source_range.end_line:
                raise ValueError('Character slicing must remain within one canonical line')
            text = selected[0].text[source_range.start_character:source_range.end_character]
        return text

    def anchors(self, source_range: SourceRange) -> list[str]:
        self._validate_range(source_range)
        return [line.html_anchor for line in self.lines[source_range.start_line - 1:source_range.end_line]]

    def anchor_for(self, source_range: SourceRange) -> str:
        return self.anchors(source_range)[0]


def _drop_invisible_and_xbrl(root) -> None:
    for node in list(root.iter()):
        name = _local_name(node.tag)
        if name in {'script', 'style', 'iframe', 'form', 'object', 'embed', 'header', 'references'}:
            node.drop_tree()
            continue
        if name == 'hidden' or _is_hidden(node):
            node.drop_tree()
    # ix elements carry display text but not source semantics.  Unwrap them after
    # hidden facts are gone so their visible descendants retain their position.
    for node in list(root.iter()):
        tag = node.tag if isinstance(node.tag, str) else ''
        if tag.lower().startswith('ix:') or _local_name(tag) in {
            'nonfraction', 'nonnumeric', 'fraction', 'continuation', 'tuple',
        }:
            node.drop_tag()
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        for attribute in list(node.attrib):
            local = _local_name(attribute)
            if (local in _XBRL_ATTRIBUTES or attribute.lower().startswith(('ix:', 'xbrli:',
                    'us-gaap:', 'dei:'))):
                del node.attrib[attribute]


def _line_nodes(root) -> Iterable[tuple[object, str]]:
    # Table rows are the atomic visible table unit; table descendants must not
    # become duplicate paragraph lines.
    query = ('//h1|//h2|//h3|//h4|//h5|//h6|//p[not(ancestor::table)]|'
             '//li[not(ancestor::table)]|//caption|//tr')
    for node in root.xpath(query):
        local = _local_name(node.tag)
        kind = ('heading' if local.startswith('h') and len(local) == 2 else
                'paragraph' if local == 'p' else
                'list_item' if local == 'li' else
                'caption' if local == 'caption' else 'table_row')
        yield node, kind


def canonicalize_html(raw_html: bytes, *, document_id: str, filing_id: str) -> tuple[CanonicalDocument, bytes]:
    """Sanitize a filing and return canonical lines plus anchor-bearing HTML."""
    try:
        root = html.document_fromstring(raw_html)
    except (etree.ParserError, ValueError) as error:
        raise ValueError('Source is not a readable HTML document') from error
    _drop_invisible_and_xbrl(root)
    tree = root.getroottree()
    source_hash = hashlib.sha256(raw_html).hexdigest()
    lines = []
    for node, kind in _line_nodes(root):
        # Browser text-content has no delimiter between adjacent table cells.
        # A visible row is instead reconstructed from its cells, preserving the
        # one-space normalization applied to every other canonical line.
        text = (normalize_visible_text(' '.join(cell.text_content() for cell in
                                       node.xpath('./th|./td')))
                if kind == 'table_row' else normalize_visible_text(node.text_content()))
        if not text:
            continue
        number = len(lines) + 1
        locator = tree.getpath(node)
        anchor = f'v2-line-{number}-{hashlib.sha256(locator.encode()).hexdigest()[:12]}'
        node.set('id', anchor)
        lines.append(CanonicalLine(line_number=number, text=text, element_type=kind,
                                   html_anchor=anchor, dom_reference=locator))
    if not lines:
        raise ValueError('HTML has no visible canonical lines')
    ref = CanonicalDocumentRef(document_id=document_id, filing_id=filing_id,
                               source_hash=source_hash, line_count=len(lines))
    return CanonicalDocument(ref=ref, lines=lines), html.tostring(root, encoding='utf-8', method='html')
