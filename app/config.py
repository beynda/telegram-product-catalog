import os
from dataclasses import dataclass, field
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    admins: frozenset[int]
    database: Path
    currency: str

    @classmethod
    def load(cls, database=ROOT / 'data/catalog.sqlite3', currency='USD'):
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
        if not re.fullmatch(r'\d{5,12}:[A-Za-z0-9_-]{30,}', token):
            raise ValueError('Set TELEGRAM_BOT_TOKEN to your own BotFather token')
        try:
            admins = frozenset(int(value) for value in os.environ.get('ADMIN_USER_IDS', '').split(',') if value.strip())
        except ValueError:
            raise ValueError('ADMIN_USER_IDS must contain comma-separated numeric Telegram IDs') from None
        if any(value <= 0 for value in admins):
            raise ValueError('Administrator IDs must be positive')
        return cls(token, admins, Path(database), currency)
