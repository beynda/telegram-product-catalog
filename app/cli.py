import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from app.catalog import CatalogRepository
from app.config import ROOT
from app.importer import import_catalog


def percentage(value):
    try:
        result = Decimal(value)
        if not result.is_finite() or not 0 <= result <= 100:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        raise argparse.ArgumentTypeError('Percentage must be between 0 and 100') from None


def currency_code(value):
    if not re.fullmatch('[A-Z]{3}', value):
        raise argparse.ArgumentTypeError('Currency must be a three-letter uppercase code, such as USD')
    return value


def main():
    parser = argparse.ArgumentParser(description='Telegram Product Catalog')
    parser.add_argument('--database', type=Path, default=ROOT / 'data/catalog.sqlite3')
    parser.add_argument('--currency', type=currency_code, default='USD')
    commands = parser.add_subparsers(dest='command', required=True)
    load = commands.add_parser('import', help='Import a local CSV price list')
    load.add_argument('file', type=Path)
    load.add_argument('--markup', type=percentage, default=Decimal('10'))
    commands.add_parser('list', help='View the saved catalog offline')
    export = commands.add_parser('export', help='Export retail prices to CSV')
    export.add_argument('file', type=Path)
    markup = commands.add_parser('markup', help='Set a percentage price rule')
    markup.add_argument('percent', type=percentage)
    scopes = markup.add_mutually_exclusive_group()
    scopes.add_argument('--category', type=int)
    scopes.add_argument('--product', type=int)
    commands.add_parser('bot', help='Start Telegram polling with your own token')
    arguments = parser.parse_args()
    repository = CatalogRepository(arguments.database)
    repository.initialize()
    try:
        if arguments.command == 'import':
            count = import_catalog(arguments.file, repository, arguments.markup)
            print(f'Imported {count} variants. Existing categories absent from the file were preserved.')
        elif arguments.command == 'markup':
            if arguments.category is not None:
                repository.set_category_markup(arguments.category, arguments.percent)
            elif arguments.product is not None:
                repository.set_section_markup(arguments.product, arguments.percent)
            else:
                repository.set_base_markup(arguments.percent)
            print('Prices updated.')
        elif arguments.command == 'bot':
            from app.config import Settings
            from app.bot import run
            if not repository.status().offer_count:
                raise ValueError('Import a CSV price list before starting the bot')
            run(Settings.load(arguments.database, arguments.currency), repository)
        else:
            rows = []
            for category in repository.list_categories():
                for product in repository.list_sections(category.id):
                    for offer in repository.list_offers(product.id):
                        rows.append([category.name, product.name, product.id, offer.variant, offer.storage or '', offer.color or '',
                                     f'{offer.retail_price // 100}.{offer.retail_price % 100:02d}', arguments.currency])
            if arguments.command == 'list':
                for row in rows:
                    print(f'[{row[2]}] {row[0]} / {row[1]} / {row[3]}: {row[7]} {row[6]}')
            else:
                arguments.file.parent.mkdir(parents=True, exist_ok=True)
                with arguments.file.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['category', 'product', 'product_id', 'variant', 'storage', 'color', 'retail_price', 'currency'])
                    for row in rows:
                        writer.writerow([("'" + cell) if isinstance(cell, str) and cell.lstrip().startswith(('=', '+', '-', '@')) else cell for cell in row])
                print(f'Exported {len(rows)} variants.')
    except (ValueError, OSError) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
