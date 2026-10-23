import json
import locale
import os

from .utils import resource_path


def detect_language():
    try:
        lang, _ = locale.getdefaultlocale()
        if lang and lang.startswith('ru'):
            return 'ru'
    except Exception:
        pass
    return 'en'


def load_translations():
    """ Load localization strings from external JSON file """
    locales_path = resource_path('locales.json')
    if not os.path.exists(locales_path):
        print(f"Warning: {locales_path} not found. Fallback to empty dictionary.")
        return {"en": {}, "ru": {}}

    try:
        with open(locales_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {locales_path}: {e}")
        return {"en": {}, "ru": {}}


LANG = detect_language()
STRINGS = load_translations()


def _t(key):
    """ Returns the translated string by key """
    return STRINGS.get(LANG, {}).get(key, key)
