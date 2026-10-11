from dataclasses import dataclass, field
from decimal import Decimal

@dataclass(frozen=True)
class ParsedOffer:
    variant: str
    storage: str | None
    color: str | None
    source_price: int
    retail_price: int
    attributes: str = ''
    notes: str = ''
    raw_line: str = ''

@dataclass
class ParsedSection:
    name: str
    offers: list[ParsedOffer] = field(default_factory=list)
    subcategory: str | None = None

@dataclass
class ParsedCatalog:
    source_key: str
    title: str
    sections: list[ParsedSection]

@dataclass(frozen=True)
class CategoryRecord:
    id: int
    name: str
    source_key: str

@dataclass(frozen=True)
class SubcategoryRecord:
    id: int
    category_id: int
    name: str

@dataclass(frozen=True)
class SectionRecord:
    id: int
    category_id: int
    name: str
    subcategory_id: int | None = None

@dataclass(frozen=True)
class OfferRecord:
    id: int
    variant: str
    storage: str | None
    color: str | None
    source_price: int
    retail_price: int
    attributes: str
    notes: str

@dataclass(frozen=True)
class MarkupRule:
    kind: str
    value: Decimal

@dataclass(frozen=True)
class CatalogStatus:
    category_count: int
    section_count: int
    offer_count: int
    updated_at: str | None
