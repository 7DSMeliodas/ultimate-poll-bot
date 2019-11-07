"""All keyboards for external users that don't own the poll."""
from telegram import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from pollbot.i18n import i18n
from pollbot.helper.enums import CallbackType


def get_help_keyboard(user, categories, current_category):
    """Get the done keyboard for options during poll creation."""
    rows = []
    current_row = []
    while len(categories) > 0:
        category = categories.pop(0)
        payload = f'{CallbackType.switch_help.value}:0:{category}'
        text = i18n.t(f'keyboard.help.{category}', locale=user.locale)
        if category == current_category:
            text = f'[ {text} ]'
        button = InlineKeyboardButton(text, callback_data=payload)

        if len(current_row) < 3:
            current_row.append(button)
        else:
            rows.append(current_row)
            current_row = [button]

    rows.append(current_row)

    return InlineKeyboardMarkup(rows)


def get_donations_keyboard():
    patreon_url = f'https://patreon.com/nukesor'
    paypal_url = f'https://paypal.me/arnebeer/'
    buttons = [
        [InlineKeyboardButton(text='Patreon', url=patreon_url)],
        [InlineKeyboardButton(text='Paypal', url=paypal_url)],
    ]

    return InlineKeyboardMarkup(buttons)
