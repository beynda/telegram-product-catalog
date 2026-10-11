import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.models import ParsedCatalog, ParsedOffer, ParsedSection
from app.pricing import apply_markup_rule

REQUIRED = {'category', 'product', 'variant', 'cost'}


def read_catalog(path: Path, repository, markup: Decimal) -> list[ParsedCatalog]:
    catalogs = {}
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError('CSV requires category, product, variant and cost columns')
        for number, row in enumerate(reader, 2):
            category, product, variant = [(row.get(key) or '').strip() for key in ('category', 'product', 'variant')]
            if not all((category, product, variant)) or any(len(value) > 120 for value in (category, product, variant)):
                raise ValueError(f'Row {number}: names must contain 1 to 120 characters')
            key = (category, product, variant)
            if key in seen:
                raise ValueError(f'Row {number}: duplicate product variant')
            seen.add(key)
            try:
                cost = Decimal(row['cost'])
                if not cost.is_finite() or cost <= 0 or cost > Decimal('10000000') or cost != cost.quantize(Decimal('0.01')):
                    raise ValueError()
                minor_cost = int(cost * 100)
            except (InvalidOperation, ValueError, TypeError):
                raise ValueError(f'Row {number}: cost must be positive with at most two decimal places') from None
            optional = {key: (row.get(key) or '').strip() for key in ('storage', 'color', 'description')}
            if any(len(value) > 500 for value in optional.values()):
                raise ValueError(f'Row {number}: optional fields must be at most 500 characters')
            catalog = catalogs.setdefault(category, ParsedCatalog('csv:' + category, category, []))
            section = next((item for item in catalog.sections if item.name == product), None)
            if section is None:
                section = ParsedSection(product)
                catalog.sections.append(section)
            rule = repository.resolve_markup_rule(catalog.source_key, product, markup)
            section.offers.append(ParsedOffer(variant, optional['storage'] or None, optional['color'] or None,
                                              minor_cost, apply_markup_rule(minor_cost, rule), notes=optional['description']))
    if not catalogs:
        raise ValueError('CSV contains no products; existing catalog was preserved')
    return list(catalogs.values())


def import_catalog(path, repository, markup):
    catalogs = read_catalog(path, repository, markup)
    repository.replace_sources(catalogs, markup)
    return sum(len(section.offers) for catalog in catalogs for section in catalog.sections)
