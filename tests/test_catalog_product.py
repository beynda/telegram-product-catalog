from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from app.bot import CatalogBot, keyboard
from app.catalog import CatalogRepository
from app.config import Settings
from app.importer import import_catalog
from app.models import ParsedCatalog, ParsedOffer, ParsedSection
from app.presenter import offer_text
from app.media import product_photo, PHOTO_ROOT, PRODUCT_PHOTOS
from app.cli import main
from unittest.mock import patch
import csv
import os


class CatalogProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.repository = CatalogRepository(self.path / 'catalog.sqlite3')
        self.repository.initialize()
        self.example = Path(__file__).resolve().parents[1] / 'examples/catalog.csv'

    def load(self):
        return import_catalog(self.example, self.repository, Decimal('10'))

    def file(self, content):
        path = self.path / 'input.csv'
        path.write_text(content, encoding='utf-8')
        return path

    def test_import_and_reimport_do_not_duplicate(self):
        self.assertEqual(self.load(), 6)
        self.load()
        self.assertEqual(self.repository.status().offer_count, 6)
        offers = self.repository.list_offers(self.repository.list_sections(1)[0].id)
        self.assertEqual(offers[0].retail_price, 32890)

    def test_invalid_final_row_preserves_entire_catalog(self):
        self.load()
        source = self.file('category,product,variant,cost\nPhones,New Phone,Blue,100\nAudio,Headphones,Black,NaN\n')
        with self.assertRaises(ValueError):
            import_catalog(source, self.repository, Decimal('10'))
        self.assertEqual(self.repository.status().offer_count, 6)
        self.assertEqual(self.repository.list_sections(1)[0].name, 'iPhone 16')

    def test_transaction_rolls_back_all_categories(self):
        self.load()
        valid = ParsedCatalog('csv:Phones', 'Phones', [ParsedSection('Replacement', [ParsedOffer('Blue', None, None, 100, 110)])])
        invalid = ParsedCatalog('csv:Audio', 'Audio', [ParsedSection('Broken', [ParsedOffer('Black', None, None, -1, 1)])])
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.replace_sources([valid, invalid])
        self.assertEqual(self.repository.status().offer_count, 6)
        self.assertEqual(self.repository.list_sections(1)[0].name, 'iPhone 16')

    def test_empty_duplicate_and_fractional_cent_rejected(self):
        for body in ['', 'Phones,Phone,Blue,12.345\n', 'Phones,Phone,Blue,10\nPhones,Phone,Blue,10\n']:
            with self.subTest(body=body), self.assertRaises(ValueError):
                import_catalog(self.file('category,product,variant,cost\n' + body), self.repository, Decimal('10'))

    def test_markup_precedence_survives_reimport(self):
        self.load()
        self.repository.set_base_markup(Decimal('20'))
        self.repository.set_category_markup(1, Decimal('15'))
        self.repository.set_section_markup(1, Decimal('5'))
        self.load()
        phone = self.repository.list_sections(1)[0]
        self.assertEqual(self.repository.list_offers(phone.id)[0].retail_price, 31395)

    def test_import_percentage_remains_base_for_other_categories(self):
        import_catalog(self.example, self.repository, Decimal('25'))
        self.repository.set_category_markup(1, Decimal('5'))
        self.assertEqual(self.repository.list_offers(3)[0].retail_price, 9988)

    def test_incomplete_csv_row_reports_validation_error(self):
        with self.assertRaises(ValueError):
            import_catalog(self.file('category,product,variant,cost\nPhones\n'), self.repository, Decimal('10'))

    def test_export_protects_spreadsheet_formulas(self):
        import_catalog(self.file('category,product,variant,cost\n=1+1,Phone,Blue,10\n'), self.repository, Decimal('10'))
        output = self.path / 'export.csv'
        with patch('sys.argv', ['catalog', '--database', str(self.repository.database_path), 'export', str(output)]):
            main()
        with output.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]['category'], "'=1+1")
        self.assertEqual(rows[0]['retail_price'], '11.00')

    def test_bundled_mapping_and_custom_photo_override(self):
        self.assertEqual(product_photo('iPhone 16', 1, self.repository.database_path), PHOTO_ROOT / 'iphone-16.jpg')
        custom = self.path / 'photos/1.jpg'
        custom.parent.mkdir()
        custom.write_bytes(b'local test image')
        self.assertEqual(product_photo('iPhone 16', 1, self.repository.database_path), custom)
        for filename in PRODUCT_PHOTOS.values():
            self.assertTrue((PHOTO_ROOT / filename).is_file())

    def test_invalid_token_and_admin_ids_are_rejected(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            Settings.load()
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '123456:' + 'a' * 35, 'ADMIN_USER_IDS': 'bad'}, clear=True), self.assertRaises(ValueError):
            Settings.load()

    def test_html_is_escaped(self):
        self.load()
        offer = self.repository.list_offers(1)[0]
        self.assertIn('&lt;script&gt;', offer_text('<script>', offer, 'USD'))

    def test_menu_pagination(self):
        items = [SimpleNamespace(id=i, name=f'Item {i}') for i in range(20)]
        rows = keyboard(items, 'category', page=1).inline_keyboard
        self.assertEqual(rows[0][0].text, 'Item 8')
        self.assertEqual([button.text for button in rows[-2]], ['Previous', 'Next'])


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'catalog.sqlite3'
        self.repository = CatalogRepository(path)
        self.repository.initialize()
        example = Path(__file__).resolve().parents[1] / 'examples/catalog.csv'
        import_catalog(example, self.repository, Decimal('10'))
        self.bot = CatalogBot(Settings('unused', frozenset({123}), path, 'USD'), self.repository)
        self.message = SimpleNamespace(reply_text=AsyncMock(), reply_photo=AsyncMock())
        self.query = SimpleNamespace(data='home', answer=AsyncMock(), edit_message_text=AsyncMock(), message=self.message)
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=123), effective_chat=SimpleNamespace(type='private'),
                                      effective_message=self.message, callback_query=self.query)

    async def test_browse_home_category_product(self):
        for data in ['home', 'category:1', 'product-1:1', 'offers:1:1']:
            self.query.data = data
            await self.bot.callback(self.update, None)
        self.assertEqual(self.query.edit_message_text.await_count, 4)
        self.assertIn('USD 383.90', self.query.edit_message_text.call_args.args[0])

    async def test_denies_unauthorized_markup(self):
        self.update.effective_user.id = 999
        await self.bot.markup(self.update, SimpleNamespace(args=['50']))
        self.assertEqual(self.repository.list_offers(1)[0].retail_price, 32890)

    async def test_admin_markup_and_nonfinite_rejection(self):
        await self.bot.markup(self.update, SimpleNamespace(args=['20']))
        self.assertEqual(self.repository.list_offers(1)[0].retail_price, 35880)
        await self.bot.markup(self.update, SimpleNamespace(args=['NaN']))
        self.assertEqual(self.repository.list_offers(1)[0].retail_price, 35880)

    async def test_search_and_stale_callback(self):
        self.message.text = 'iphone'
        await self.bot.search(self.update, None)
        self.assertIn('2 products found', self.message.reply_text.call_args.args[0])
        self.query.data = 'product-1:9999'
        await self.bot.callback(self.update, None)
        self.assertIn('updated', self.message.reply_text.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
