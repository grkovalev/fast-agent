"""Bounded, read-only projections of saved fact inspection provenance."""
from profitlab.v2.contracts import FactPresentation, FactSourceMapping


def presentation_preview(presentation: FactPresentation) -> dict:
    data = presentation.model_dump(mode='json', exclude={'locations', 'numeric_records'})
    data['diagnostics'] = [text[:500] for text in presentation.diagnostics[:5]]
    data['locations'] = [location.model_dump(mode='json')
                         for location in presentation.locations[:20]]
    for location in data['locations']:
        location['filer_label'] = location['filer_label'][:500]
    data['location_count'] = len(presentation.locations)
    data['truncated'] = (len(presentation.locations) > 20 or len(presentation.diagnostics) > 5
                         or any(len(text) > 500 for text in presentation.diagnostics)
                         or any(len(location.filer_label) > 500 for location in presentation.locations[:20]))
    return data


def source_preview(mapping: FactSourceMapping) -> dict:
    """Keep full occurrence records on the paginated mapping page."""
    locations = []
    truncated = len(mapping.locations) > 3 or len(mapping.diagnostics) > 5
    for location in mapping.locations[:3]:
        data = location.model_dump(mode='json', include={
            'source_range', 'html_anchor', 'quote', 'cell_text', 'period_start',
            'period_end', 'unit', 'scale', 'sign', 'transformed_value', 'header_context',
        })
        for field in ('quote', 'cell_text'):
            truncated |= len(data[field]) > 1200
            data[field] = data[field][:1200]
        truncated |= len(data['header_context']) > 6 or any(
            len(text) > 400 for text in data['header_context'])
        data['header_context'] = [text[:400] for text in data['header_context'][:6]]
        locations.append(data)
    truncated |= any(len(text) > 500 for text in mapping.diagnostics)
    return {
        'status': mapping.status, 'method': mapping.method,
        'location_count': len(mapping.locations), 'locations': locations,
        'diagnostics': [text[:500] for text in mapping.diagnostics[:5]],
        'truncated': truncated,
    }
