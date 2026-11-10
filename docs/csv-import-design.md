# Updating a Telegram catalog from CSV without leaving a partially updated price list

By Beynda. An engineering note about the open-source Telegram Product Catalog demonstration project.

A bad row at the end of a price list should not leave earlier categories updated and the rest unchanged. Our Telegram Product Catalog handles this in two stages: validate the entire CSV first, then write all included categories in a single SQLite transaction.

## The risk of saving as you read

Consider a file with two categories. The first is valid, but a product in the second has a negative price. If an importer saves each row immediately, the resulting catalog can contain a mixture of old and new prices. Displaying an error does not restore the original data.

The important design decision is therefore broader than accepting a CSV: define what gets replaced, what remains untouched and what a failed import means. We separated input validation from database updates to make those rules explicit.

## Validate before changing the catalog

The importer requires category, product, variant and cost fields. It checks names, duplicate combinations and valid prices. An empty file is rejected rather than interpreted as a request to clear the catalog.

Category replacement is not called until the whole file passes validation. An invalid final row leaves the previous catalog intact, allowing the operator to correct the file and try again.

## Commit the included categories together

Validated categories are processed within one SQLite transaction. If a later category fails during the database update, earlier updates from that import are rolled back.

This is not a full inventory synchronization policy. Categories included in the file are replaced; categories missing from it are retained. A business that needs missing products removed requires a different, explicitly designed rule. That behavior should be visible to the operator rather than inferred from the upload button.

## A small failure example

Consider this synthetic input:

```csv
category,product,variant,cost
Audio,Headphones,Black,50.00
Accessories,USB cable,White,-5.00
```

The second product has an invalid cost. The expected outcome is a rejected import and an unchanged catalog, including the Audio category. The importer validates both rows before calling the database replacement method.

The implementation lives in [app/importer.py](../app/importer.py) and [app/catalog.py](../app/catalog.py). Regression cases are in [tests/test_catalog_product.py](../tests/test_catalog_product.py).

## Keep pricing rules explicit

Money is stored in integer minor units. Percentage calculations use a defined rounding rule. Product-specific markup overrides category markup, which overrides the base setting.

Saved markup rules survive reimports. However, renaming a category or product changes its matching key. Renaming therefore needs attention if a business expects all previous pricing settings to follow the new name automatically.

## What we verified

Local tests cover invalid final rows, transaction rollback, repeated imports without duplicates and markup precedence. All 23 tests of the public version passed again on November 10, 2026.

Telegram calls are mocked in these tests. This verifies application logic, not a live bot session or production load. The README recommends stopping the bot before importing to avoid stale menu buttons pointing to changed data.

## Where this approach fits

The public project provides category and product browsing, search and a local retail-price export. It does not include checkout, payments, inventory tracking or automatic supplier synchronization.

For a similar business tool, agree on the data-update rules before building the menus. A reproducible failure case that preserves existing data is more useful than a one-click upload promise with undefined consequences.

Source code and instructions: [Telegram Product Catalog](https://github.com/beynda/telegram-product-catalog). The code is MIT-licensed; product images have separate usage terms.

[Beynda: websites, software tools and business automation](https://beynda.com/en/)
