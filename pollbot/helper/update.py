"""Update or delete poll messages."""
from datetime import datetime, timedelta
from telegram.error import BadRequest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation

from pollbot.i18n import i18n
from pollbot.telegram.keyboard import get_management_keyboard
from pollbot.helper.enums import ExpectedInput
from pollbot.display import (
    get_poll_text_and_vote_keyboard,
)
from pollbot.models import Update

flood_threshold = 60
window_size = 2


def update_poll_messages(session, bot, poll):
    """Logic for handling updates."""
    # Round the current time to the nearest time window
    now = datetime.now()
    time_window = now - timedelta(seconds=now.second % window_size, microseconds=now.microsecond)
    one_minute_ago = time_window - timedelta(minutes=1)

    # Check whether we have a new window
    current_update = session.query(Update) \
        .filter(Update.poll == poll) \
        .filter(Update.time_window == time_window) \
        .one_or_none()

    updates_in_last_minute = session.query(func.sum(Update.count)) \
        .filter(Update.poll == poll) \
        .filter(Update.time_window >= one_minute_ago) \
        .one()[0]

    if updates_in_last_minute is None:
        updates_in_last_minute = 0

    # No window yet, we need to create it
    if current_update is None:
        try:
            # Create and commit update.
            # This automatically schedules the update and might result in a double
            # update, if the job runs at practically the same time.
            # The worst case scenario is a Message is not modified exception.
            current_update = Update(poll, time_window)
            session.add(current_update)
            session.commit()

            # We are below the flood_limit, just update it
            if updates_in_last_minute <= flood_threshold:
                # Try to send updates
                send_updates(session, bot, poll)

                # If that succeeded, set updated to true and increase count
                # Update inside of mysql to avoid race conditions between threads
                session.query(Update) \
                    .filter(Update.id == current_update.id) \
                    .update({
                        'count': Update.count + 1,
                        'updated': True,
                    })

        except (IntegrityError, UniqueViolation):
            # The update has been already created in another thread
            # Get the update and work with this instance
            session.rollback()
            current_update = session.query(Update) \
                .filter(Update.poll == poll) \
                .filter(Update.time_window == time_window) \
                .one()

    # The update should be updated again
    elif current_update and current_update.updated:
        try:
            # We are still below the flood_threshold, update directrly
            if updates_in_last_minute <= flood_threshold:
                if updates_in_last_minute == flood_threshold:
                    send_updates(session, bot, poll, show_warning=True)
                else:
                    send_updates(session, bot, poll)

                # Update inside of mysql to avoid race conditions between threads
                session.query(Update) \
                    .filter(Update.id == current_update.id) \
                    .update({'count': Update.count + 1})

            # Reschedule the update, the job will increment the count
            else:
                current_update.updated = False
        except Exception as e:
            # Some error occurred during updating of the message.
            # Set the updated flag to False to reschedule the update!
            current_update.updated = False
            # Commit here for now and raise e. Just for temporary debugging and monitoring purposes
            session.commit()
            raise e

    # The next update is already scheduled
    elif current_update and not current_update.updated:
        pass

    session.commit()


def send_updates(session, bot, poll, show_warning=False):
    """Actually update all messages."""
    for reference in poll.references:
        try:
            # Admin poll management interface
            if reference.admin_message_id is not None and not poll.in_settings:
                text, keyboard = get_poll_text_and_vote_keyboard(session, poll, show_warning, show_back=True)

                if poll.user.expected_input != ExpectedInput.votes.name:
                    keyboard = get_management_keyboard(poll)

                bot.edit_message_text(
                    text,
                    chat_id=reference.admin_chat_id,
                    message_id=reference.admin_message_id,
                    reply_markup=keyboard,
                    parse_mode='markdown',
                    disable_web_page_preview=True,
                )

            # Edit message via inline_message_id
            elif reference.inline_message_id is not None:
                # Create text and keyboard
                text, keyboard = get_poll_text_and_vote_keyboard(session, poll, show_warning)

                bot.edit_message_text(
                    text,
                    inline_message_id=reference.inline_message_id,
                    reply_markup=keyboard,
                    parse_mode='markdown',
                    disable_web_page_preview=True,
                )
        except BadRequest as e:
            if e.message.startswith('Message_id_invalid') or \
                   e.message.startswith("Message can't be edited") or \
                   e.message.startswith("Message to edit not found") or \
                   e.message.startswith("Chat not found"):
                session.delete(reference)
                session.commit()
            elif e.message.startswith('Message is not modified'):
                pass
            else:
                raise


def remove_poll_messages(session, bot, poll):
    """Remove all messages (references) of a poll."""
    for reference in poll.references:
        try:
            # Admin poll management interface
            if reference.inline_message_id is None:
                bot.edit_message_text(
                    i18n.t('deleted.poll', locale=poll.locale),
                    chat_id=reference.admin_chat_id,
                    message_id=reference.admin_message_id,
                )

            # Edit message via inline_message_id
            else:
                # Create text and keyboard
                bot.edit_message_text(
                    i18n.t('deleted.poll', locale=poll.locale),
                    inline_message_id=reference.inline_message_id,
                )
        except BadRequest as e:
            if e.message.startswith('Message_id_invalid'):
                pass
            else:
                raise
