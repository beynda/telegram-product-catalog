from html import escape


def price(value, currency):
    return f'{currency} {value / 100:,.2f}'


def offer_text(product, offer, currency):
    details = ' / '.join(value for value in (offer.storage, offer.color) if value)
    lines = [f'<b>{escape(product)}</b>', escape(offer.variant)]
    if details:
        lines.append(escape(details))
    lines.append(f'<b>{price(offer.retail_price, currency)}</b>')
    if offer.notes:
        lines.extend(['', escape(offer.notes)])
    return '\n'.join(lines)
