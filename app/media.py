from pathlib import Path

PHOTO_ROOT = Path(__file__).resolve().parents[1] / 'assets/product_photos'

PRODUCT_PHOTOS = {
    'iphone 15': 'iphone-15.jpg',
    'iphone 16': 'iphone-16.jpg',
    'iphone 16 plus': 'iphone-16.jpg',
    'iphone 16 pro': 'iphone-16-pro.jpg',
    'iphone 16 pro max': 'iphone-16-pro.jpg',
    'iphone 17e': 'iphone-17e.jpg',
    'iphone 17': 'iphone-17.jpg',
    'iphone air': 'iphone-air.jpg',
    'iphone 17 pro': 'iphone-17-pro.jpg',
    'iphone 17 pro max': 'iphone-17-pro.jpg',
    'samsung galaxy s25': 'samsung-s25.jpg',
    'samsung galaxy s25 fe': 'samsung-s25-fe.jpg',
    'samsung galaxy s25 ultra': 'samsung-s25-ultra.jpg',
    'samsung galaxy s26': 'samsung-s26.jpg',
    'samsung galaxy s26 plus': 'samsung-s26-plus.jpg',
    'samsung galaxy s26 ultra': 'samsung-s26-ultra.jpg',
    'samsung galaxy a37': 'samsung-a37.jpg',
    'samsung galaxy a57': 'samsung-a57.jpg',
    'airpods 4': 'airpods.jpg',
    'airpods pro': 'airpods-pro.jpg',
    'airpods max': 'airpods-max.jpg',
    'playstation 5': 'ps5.jpg',
    'ray-ban meta': 'rayban-meta.jpg',
    'instax': 'instax.jpg',
    'canon': 'canon.jpg',
}


def product_photo(product_name, product_id, database):
    custom = database.parent / 'photos' / f'{product_id}.jpg'
    if custom.is_file():
        return custom
    filename = PRODUCT_PHOTOS.get(' '.join(product_name.casefold().split()))
    if filename:
        path = PHOTO_ROOT / filename
        if path.is_file():
            return path
    return None
