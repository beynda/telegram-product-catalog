import sqlite3
from contextlib import closing, nullcontext
from decimal import Decimal
from pathlib import Path
from app.models import CatalogStatus, CategoryRecord, MarkupRule, OfferRecord, ParsedCatalog, SectionRecord, SubcategoryRecord
from app.pricing import apply_markup_rule


class CatalogRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY,
                    source_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS subcategories (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    UNIQUE(category_id, name)
                );
                CREATE TABLE IF NOT EXISTS sections (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    UNIQUE(category_id, name)
                );
                CREATE TABLE IF NOT EXISTS offers (
                    id INTEGER PRIMARY KEY,
                    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
                    variant TEXT NOT NULL,
                    storage TEXT,
                    color TEXT,
                    source_price INTEGER NOT NULL CHECK(source_price > 0),
                    retail_price INTEGER NOT NULL CHECK(retail_price > 0),
                    attributes TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sections_category ON sections(category_id, position);
                CREATE INDEX IF NOT EXISTS idx_offers_section ON offers(section_id, position);
                CREATE TABLE IF NOT EXISTS markup_rules (
                    scope TEXT NOT NULL CHECK(scope IN ('base', 'category', 'section')),
                    source_key TEXT NOT NULL DEFAULT '',
                    section_name TEXT NOT NULL DEFAULT '',
                    percent TEXT NOT NULL,
                    PRIMARY KEY(scope, source_key, section_name)
                );
                CREATE TABLE IF NOT EXISTS fixed_markup_rules (
                    scope TEXT NOT NULL CHECK(scope IN ('base', 'category', 'section')),
                    source_key TEXT NOT NULL DEFAULT '',
                    section_name TEXT NOT NULL DEFAULT '',
                    amount INTEGER NOT NULL,
                    PRIMARY KEY(scope, source_key, section_name)
                );
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(sections)")}
            if "subcategory_id" not in columns:
                connection.execute("ALTER TABLE sections ADD COLUMN subcategory_id INTEGER")
            connection.commit()

    def replace_source(self, catalog: ParsedCatalog, connection=None) -> None:
        if not catalog.sections or not any(section.offers for section in catalog.sections):
            raise ValueError("Cannot replace a catalog with an empty snapshot")

        owned = connection is None
        with (closing(self._connect()) if owned else nullcontext(connection)) as connection:
            with (connection if owned else nullcontext()):
                existing = connection.execute(
                    "SELECT id FROM categories WHERE source_key = ?", (catalog.source_key,)
                ).fetchone()
                if existing:
                    category_id = int(existing["id"])
                    connection.execute(
                        "UPDATE categories SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (catalog.title, category_id),
                    )
                    connection.execute("DELETE FROM sections WHERE category_id = ?", (category_id,))
                    connection.execute(
                        "DELETE FROM subcategories WHERE category_id = ?", (category_id,)
                    )
                else:
                    cursor = connection.execute(
                        "INSERT INTO categories(source_key, name) VALUES (?, ?)",
                        (catalog.source_key, catalog.title),
                    )
                    category_id = int(cursor.lastrowid)

                subcategory_ids: dict[str, int] = {}
                for section_position, section in enumerate(catalog.sections):
                    subcategory_id: int | None = None
                    if section.subcategory:
                        if section.subcategory not in subcategory_ids:
                            cursor = connection.execute(
                                "INSERT INTO subcategories(category_id, name, position) VALUES (?, ?, ?)",
                                (category_id, section.subcategory, len(subcategory_ids)),
                            )
                            subcategory_ids[section.subcategory] = int(cursor.lastrowid)
                        subcategory_id = subcategory_ids[section.subcategory]

                    cursor = connection.execute(
                        "INSERT INTO sections(category_id, name, position, subcategory_id) VALUES (?, ?, ?, ?)",
                        (category_id, section.name, section_position, subcategory_id),
                    )
                    section_id = int(cursor.lastrowid)
                    for offer_position, offer in enumerate(section.offers):
                        connection.execute(
                            """
                            INSERT INTO offers(
                                section_id, variant, storage, color, source_price,
                                retail_price, attributes, notes, position
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                section_id,
                                offer.variant,
                                offer.storage,
                                offer.color,
                                offer.source_price,
                                offer.retail_price,
                                offer.attributes,
                                offer.notes,
                                offer_position,
                            ),
                        )

    def list_categories(self) -> list[CategoryRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, name, source_key FROM categories ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [CategoryRecord(int(row["id"]), row["name"], row["source_key"]) for row in rows]

    def get_category(self, category_id: int) -> CategoryRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, name, source_key FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
        if row is None:
            return None
        return CategoryRecord(int(row["id"]), row["name"], row["source_key"])

    def list_sections(self, category_id: int) -> list[SectionRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, category_id, name, subcategory_id FROM sections "
                "WHERE category_id = ? ORDER BY position",
                (category_id,),
            ).fetchall()
        return [
            SectionRecord(int(row["id"]), int(row["category_id"]), row["name"], row["subcategory_id"])
            for row in rows
        ]

    def get_section(self, section_id: int) -> SectionRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, category_id, name, subcategory_id FROM sections WHERE id = ?", (section_id,)
            ).fetchone()
        if row is None:
            return None
        return SectionRecord(int(row["id"]), int(row["category_id"]), row["name"], row["subcategory_id"])

    def list_subcategories(self, category_id: int) -> list[SubcategoryRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, category_id, name FROM subcategories WHERE category_id = ? ORDER BY position",
                (category_id,),
            ).fetchall()
        return [
            SubcategoryRecord(int(row["id"]), int(row["category_id"]), row["name"]) for row in rows
        ]

    def get_subcategory(self, subcategory_id: int) -> SubcategoryRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, category_id, name FROM subcategories WHERE id = ?", (subcategory_id,)
            ).fetchone()
        if row is None:
            return None
        return SubcategoryRecord(int(row["id"]), int(row["category_id"]), row["name"])

    def list_sections_for_subcategory(self, subcategory_id: int) -> list[SectionRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, category_id, name, subcategory_id FROM sections "
                "WHERE subcategory_id = ? ORDER BY position",
                (subcategory_id,),
            ).fetchall()
        return [
            SectionRecord(int(row["id"]), int(row["category_id"]), row["name"], row["subcategory_id"])
            for row in rows
        ]

    def list_storages(self, section_id: int) -> list[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT storage FROM offers
                WHERE section_id = ? AND storage IS NOT NULL
                ORDER BY CAST(REPLACE(REPLACE(storage, '/', ''), 'TB', '9999') AS INTEGER), storage
                """,
                (section_id,),
            ).fetchall()
        return [str(row["storage"]) for row in rows]

    def list_offers(self, section_id: int, storage: str | None = None) -> list[OfferRecord]:
        query = """
            SELECT id, variant, storage, color, source_price, retail_price, attributes, notes
            FROM offers WHERE section_id = ?
        """
        parameters: list[object] = [section_id]
        if storage is not None:
            query += " AND storage = ?"
            parameters.append(storage)
        query += " ORDER BY COALESCE(color, variant) COLLATE NOCASE, retail_price"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            OfferRecord(
                int(row["id"]),
                row["variant"],
                row["storage"],
                row["color"],
                int(row["source_price"]),
                int(row["retail_price"]),
                row["attributes"],
                row["notes"],
            )
            for row in rows
        ]

    def status(self) -> CatalogStatus:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM categories) AS categories,
                    (SELECT COUNT(*) FROM sections) AS sections,
                    (SELECT COUNT(*) FROM offers) AS offers,
                    (SELECT MAX(updated_at) FROM categories) AS updated_at
                """
            ).fetchone()
        assert row is not None
        return CatalogStatus(
            int(row["categories"]),
            int(row["sections"]),
            int(row["offers"]),
            row["updated_at"],
        )

    @staticmethod
    def _validate_markup(percent: Decimal) -> Decimal:
        value = Decimal(str(percent))
        if not value.is_finite() or value < 0 or value > 100:
            raise ValueError("Markup must be between 0 and 100 percent")
        return value

    @staticmethod
    def _validate_fixed_markup(amount: int) -> int:
        value = int(amount)
        if value < 0:
            raise ValueError("Fixed markup cannot be negative")
        return value

    @staticmethod
    def _rules(connection: sqlite3.Connection) -> dict[tuple[str, str, str], Decimal]:
        rows = connection.execute(
            "SELECT scope, source_key, section_name, percent FROM markup_rules"
        ).fetchall()
        return {
            (row["scope"], row["source_key"], row["section_name"]): Decimal(row["percent"])
            for row in rows
        }

    @staticmethod
    def _fixed_rules(connection: sqlite3.Connection) -> dict[tuple[str, str, str], int]:
        rows = connection.execute(
            "SELECT scope, source_key, section_name, amount FROM fixed_markup_rules"
        ).fetchall()
        return {
            (row["scope"], row["source_key"], row["section_name"]): int(row["amount"])
            for row in rows
        }

    @staticmethod
    def _resolved_from_rules(
        rules: dict[tuple[str, str, str], Decimal],
        source_key: str,
        section_name: str,
        default: Decimal,
    ) -> Decimal:
        return rules.get(
            ("section", source_key, section_name),
            rules.get(
                ("category", source_key, ""),
                rules.get(("base", "", ""), default),
            ),
        )

    @staticmethod
    def _resolved_rule(
        percent_rules: dict[tuple[str, str, str], Decimal],
        fixed_rules: dict[tuple[str, str, str], int],
        source_key: str,
        section_name: str,
        default_percent: Decimal,
    ) -> MarkupRule:
        for scope, key in (
            ("section", (source_key, section_name)),
            ("category", (source_key, "")),
            ("base", ("", "")),
        ):
            lookup = (scope, *key)
            if lookup in fixed_rules:
                return MarkupRule("fixed", Decimal(fixed_rules[lookup]))
            if lookup in percent_rules:
                return MarkupRule("percent", percent_rules[lookup])
        return MarkupRule("percent", default_percent)

    def resolve_markup(
        self,
        source_key: str,
        section_name: str,
        default: Decimal,
    ) -> Decimal:
        with closing(self._connect()) as connection:
            rules = self._rules(connection)
        return self._resolved_from_rules(rules, source_key, section_name, Decimal(str(default)))

    def resolve_markup_rule(
        self,
        source_key: str,
        section_name: str,
        default_percent: Decimal,
    ) -> MarkupRule:
        with closing(self._connect()) as connection:
            percent_rules = self._rules(connection)
            fixed_rules = self._fixed_rules(connection)
        return self._resolved_rule(
            percent_rules, fixed_rules, source_key, section_name, Decimal(str(default_percent))
        )

    def get_base_markup_rule(self, default_percent: Decimal) -> MarkupRule:
        with closing(self._connect()) as connection:
            percent_rules = self._rules(connection)
            fixed_rules = self._fixed_rules(connection)
        if ("base", "", "") in fixed_rules:
            return MarkupRule("fixed", Decimal(fixed_rules[("base", "", "")]))
        return MarkupRule(
            "percent", percent_rules.get(("base", "", ""), Decimal(str(default_percent)))
        )

    def list_markup_rules(self) -> dict[tuple[str, str, str], Decimal]:
        with closing(self._connect()) as connection:
            return self._rules(connection)

    def list_fixed_markup_rules(self) -> dict[tuple[str, str, str], int]:
        with closing(self._connect()) as connection:
            return self._fixed_rules(connection)

    def _reprice(self, connection: sqlite3.Connection, default: Decimal) -> None:
        percent_rules = self._rules(connection)
        fixed_rules = self._fixed_rules(connection)
        rows = connection.execute(
            """
            SELECT o.id, o.source_price, c.source_key, s.name AS section_name
            FROM offers o
            JOIN sections s ON s.id = o.section_id
            JOIN categories c ON c.id = s.category_id
            """
        ).fetchall()
        for row in rows:
            rule = self._resolved_rule(
                percent_rules,
                fixed_rules,
                row["source_key"],
                row["section_name"],
                default,
            )
            connection.execute(
                "UPDATE offers SET retail_price = ? WHERE id = ?",
                (apply_markup_rule(int(row["source_price"]), rule), int(row["id"])),
            )

    def _set_rule(
        self,
        scope: str,
        source_key: str,
        section_name: str,
        percent: Decimal,
    ) -> None:
        value = self._validate_markup(percent)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO markup_rules(scope, source_key, section_name, percent)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(scope, source_key, section_name)
                    DO UPDATE SET percent = excluded.percent
                    """,
                    (scope, source_key, section_name, str(value)),
                )
                # A scope can only carry one active rule at a time.
                connection.execute(
                    "DELETE FROM fixed_markup_rules WHERE scope = ? AND source_key = ? AND section_name = ?",
                    (scope, source_key, section_name),
                )
                base = self._rules(connection).get(("base", "", ""), Decimal("10"))
                self._reprice(connection, base)

    def _set_fixed_rule(
        self,
        scope: str,
        source_key: str,
        section_name: str,
        amount: int,
    ) -> None:
        value = self._validate_fixed_markup(amount)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO fixed_markup_rules(scope, source_key, section_name, amount)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(scope, source_key, section_name)
                    DO UPDATE SET amount = excluded.amount
                    """,
                    (scope, source_key, section_name, value),
                )
                # A scope can only carry one active rule at a time.
                connection.execute(
                    "DELETE FROM markup_rules WHERE scope = ? AND source_key = ? AND section_name = ?",
                    (scope, source_key, section_name),
                )
                base = self._rules(connection).get(("base", "", ""), Decimal("10"))
                self._reprice(connection, base)

    def set_base_markup(self, percent: Decimal) -> None:
        self._set_rule("base", "", "", percent)

    def set_base_markup_fixed(self, amount: int) -> None:
        self._set_fixed_rule("base", "", "", amount)

    def set_category_markup(self, category_id: int, percent: Decimal) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT source_key FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Category not found")
        self._set_rule("category", row["source_key"], "", percent)

    def set_category_markup_fixed(self, category_id: int, amount: int) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT source_key FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Category not found")
        self._set_fixed_rule("category", row["source_key"], "", amount)

    def set_section_markup(self, section_id: int, percent: Decimal) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT c.source_key, s.name
                FROM sections s JOIN categories c ON c.id = s.category_id
                WHERE s.id = ?
                """,
                (section_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Product not found")
        self._set_rule("section", row["source_key"], row["name"], percent)

    def set_section_markup_fixed(self, section_id: int, amount: int) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT c.source_key, s.name
                FROM sections s JOIN categories c ON c.id = s.category_id
                WHERE s.id = ?
                """,
                (section_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Product not found")
        self._set_fixed_rule("section", row["source_key"], row["name"], amount)

    def _clear_rule(self, scope: str, source_key: str, section_name: str) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM markup_rules WHERE scope = ? AND source_key = ? AND section_name = ?",
                    (scope, source_key, section_name),
                )
                connection.execute(
                    "DELETE FROM fixed_markup_rules WHERE scope = ? AND source_key = ? AND section_name = ?",
                    (scope, source_key, section_name),
                )
                base = self._rules(connection).get(("base", "", ""), Decimal("10"))
                self._reprice(connection, base)

    def clear_category_markup(self, category_id: int) -> None:
        category = next((item for item in self.list_categories() if item.id == category_id), None)
        if category is None:
            raise ValueError("Category not found")
        self._clear_rule("category", category.source_key, "")

    def clear_section_markup(self, section_id: int) -> None:
        section = self.get_section(section_id)
        if section is None:
            raise ValueError("Product not found")
        category = next(
            (item for item in self.list_categories() if item.id == section.category_id),
            None,
        )
        if category is None:
            raise ValueError("Category not found")
        self._clear_rule("section", category.source_key, section.name)

    def replace_sources(self, catalogs, default_markup=None):
        with closing(self._connect()) as connection:
            with connection:
                for catalog in catalogs:
                    self.replace_source(catalog, connection)
                if default_markup is not None:
                    value = self._validate_markup(default_markup)
                    connection.execute(
                        "INSERT OR IGNORE INTO markup_rules(scope, source_key, section_name, percent) "
                        "VALUES ('base', '', '', ?)", (str(value),)
                    )

