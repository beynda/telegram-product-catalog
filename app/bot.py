import logging
import re
from decimal import Decimal, InvalidOperation
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.presenter import offer_text
from app.media import product_photo
from app.rate_limit import UserRateLimiter

PAGE_SIZE = 8


def keyboard(items, prefix, page=0, back='home'):
    page = max(0, min(page, max(0, (len(items) - 1) // PAGE_SIZE)))
    start = page * PAGE_SIZE
    rows = [[InlineKeyboardButton(item.name, callback_data=f'{prefix}:{item.id}')] for item in items[start:start + PAGE_SIZE]]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton('Previous', callback_data=f'page:{prefix}:{page - 1}'))
    if start + PAGE_SIZE < len(items):
        navigation.append(InlineKeyboardButton('Next', callback_data=f'page:{prefix}:{page + 1}'))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton('Back to catalog', callback_data=back)])
    return InlineKeyboardMarkup(rows)


class CatalogBot:
    def __init__(self, settings, repository):
        self.settings = settings
        self.repository = repository
        self.limiter = UserRateLimiter()

    async def start(self, update, context):
        await update.effective_message.reply_text('Product catalog\nChoose a category, or send a product name to search.',
            reply_markup=keyboard(self.repository.list_categories(), 'category'))

    async def callback(self, update, context):
        query = update.callback_query
        data = query.data or ''
        if not self.limiter.allow(update.effective_user.id):
            await query.answer('Please wait a moment.', show_alert=True)
            return
        await query.answer()
        try:
            if data == 'home' or re.fullmatch(r'page:category:\d{1,6}', data):
                page = int(data.rsplit(':', 1)[1]) if data != 'home' else 0
                text = 'Product catalog\nChoose a category, or send a product name to search.'
                markup = keyboard(self.repository.list_categories(), 'category', page)
            elif re.fullmatch(r'category:\d{1,10}|page:product-\d{1,10}:\d{1,6}', data):
                if data.startswith('category:'):
                    category_id, page = int(data.split(':')[1]), 0
                else:
                    category_id, page = int(data.split(':')[1].split('-')[1]), int(data.split(':')[2])
                category = self.repository.get_category(category_id)
                if category is None:
                    raise ValueError('This category was updated. Use /start to reload.')
                text = escape(category.name)
                markup = keyboard(self.repository.list_sections(category_id), f'product-{category_id}', page)
            elif re.fullmatch(r'product-\d{1,10}:\d{1,10}|offers:\d{1,10}:\d{1,6}', data):
                product_id = int(data.split(':')[1])
                page = int(data.split(':')[2]) if data.startswith('offers:') else 0
                product = self.repository.get_section(product_id)
                if product is None:
                    raise ValueError('This product was updated. Use /start to reload.')
                offers = self.repository.list_offers(product_id)
                page = max(0, min(page, max(0, len(offers) - 1)))
                if not offers:
                    raise ValueError('No available variants.')
                text = offer_text(product.name, offers[page], self.settings.currency)
                rows = []
                nav = []
                if page:
                    nav.append(InlineKeyboardButton('Previous variant', callback_data=f'offers:{product_id}:{page - 1}'))
                if page + 1 < len(offers):
                    nav.append(InlineKeyboardButton('Next variant', callback_data=f'offers:{product_id}:{page + 1}'))
                if nav:
                    rows.append(nav)
                rows.append([InlineKeyboardButton('Back to products', callback_data=f'category:{product.category_id}')])
                markup = InlineKeyboardMarkup(rows)
                await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
                photo = product_photo(product.name, product_id, self.settings.database)
                if photo is not None and not data.startswith('offers:'):
                    with photo.open('rb') as stream:
                        await query.message.reply_photo(stream)
                return
            else:
                raise ValueError('Unknown action. Use /start to reload.')
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        except ValueError as error:
            await query.message.reply_text(str(error))
        except BadRequest as error:
            if 'message is not modified' not in str(error).lower():
                raise

    async def search(self, update, context):
        if not self.limiter.allow(update.effective_user.id):
            await update.effective_message.reply_text('Please wait a moment.')
            return
        term = (update.effective_message.text or '').strip().casefold()
        if len(term) < 2 or len(term) > 120:
            await update.effective_message.reply_text('Enter 2 to 120 characters to search product names.')
            return
        matches = [item for category in self.repository.list_categories() for item in self.repository.list_sections(category.id) if term in item.name.casefold()]
        rows = [[InlineKeyboardButton(item.name, callback_data=f'product-{item.category_id}:{item.id}')] for item in matches[:20]]
        rows.append([InlineKeyboardButton('Catalog', callback_data='home')])
        await update.effective_message.reply_text(f'{len(matches)} products found. Showing up to 20.', reply_markup=InlineKeyboardMarkup(rows))

    async def markup(self, update, context):
        if update.effective_user.id not in self.settings.admins or update.effective_chat.type != 'private':
            await update.effective_message.reply_text('Administrator access in a private chat is required.')
            return
        try:
            if len(context.args) != 1:
                raise ValueError('Use /markup 15 to apply a base percentage from 0 to 100.')
            value = Decimal(context.args[0])
            if not value.is_finite() or not 0 <= value <= 100:
                raise ValueError('Markup must be between 0 and 100 percent.')
            self.repository.set_base_markup(value)
            await update.effective_message.reply_text(f'Base markup updated to {value}%.')
        except (InvalidOperation, ValueError) as error:
            await update.effective_message.reply_text(str(error) if isinstance(error, ValueError) else 'Enter a valid percentage.')


def run(settings, repository):
    controller = CatalogBot(settings, repository)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    application = Application.builder().token(settings.token).build()
    application.add_handler(CommandHandler('start', controller.start))
    application.add_handler(CommandHandler('markup', controller.markup))
    application.add_handler(CallbackQueryHandler(controller.callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.search))
    application.run_polling()
