import os
import re
import shutil
from datetime import timedelta, date, datetime
from telethon.tl.types import User


def sanitize_folder_name(name):
    invalid_chars_pattern = r'[<>:"/\\|?*\x00-\x1F]'
    sanitized = re.sub(invalid_chars_pattern, '', name)

    sanitized = sanitized.rstrip('. ')
    if not sanitized:
        return '_'

    return sanitized


def save_messages(user_dir, file_name, messages):
    file_path = os.path.join(user_dir, file_name)
    messages = reversed(messages)
    with open(file_path, 'w', encoding='utf-8') as file:
        for msg in messages:
            time_str = msg.date.strftime('%d.%m %H:%M:%S')
            direction = 'Исходящее' if msg.out else 'Входящее '
            content = msg.text or f"<{msg.message or 'Не текстовое сообщ.'}>"
            lines = content.split('\n')
            first_line = f"[{time_str}] ({direction}) {lines[0]}"
            file.write(f"{first_line}\n")
            indent_length = len(f"[{time_str}] ({direction}) ")
            for line in lines[1:]:
                indented_line = ' ' * indent_length + line
                file.write(f"{indented_line}\n")


def calculate_time_spent(messages, work_start, work_end):
    typing_speed = 200  # symbols per minute
    reading_speed = 170  # words per minute

    total_typing_symbols = 0
    total_reading_words = 0
    total_incoming_messages = 0
    total_outgoing_messages = 0
    total_incoming_symbols = 0
    total_outgoing_symbols = 0

    r_times_working = []
    r_times_night = []
    messages_without_reply = 0

    # Ensure messages are in chronological order (from earliest to latest)
    messages_sorted = sorted(messages, key=lambda m: m.date)

    awaiting_reply = False
    last_incoming_datetime = None

    for msg in messages_sorted:
        if msg.text:
            if not msg.out:
                # Incoming message
                total_incoming_messages += 1
                total_incoming_symbols += len(msg.text)
                total_reading_words += len(msg.text.split())

                last_incoming_datetime = msg.date
                awaiting_reply = True
            else:
                # Outgoing message
                total_outgoing_messages += 1
                total_outgoing_symbols += len(msg.text)
                total_typing_symbols += len(msg.text)

                if awaiting_reply:
                    last_incoming_date = last_incoming_datetime.date()
                    work_start_datetime = datetime.combine(last_incoming_date, work_start, tzinfo=last_incoming_datetime.tzinfo)
                    work_end_datetime = datetime.combine(last_incoming_date, work_end, tzinfo=last_incoming_datetime.tzinfo)

                    if last_incoming_datetime >= work_start_datetime and msg.date <= work_end_datetime:
                        r_times_working.append((msg.date - last_incoming_datetime).total_seconds())
                    else:
                        r_times_night.append((msg.date - last_incoming_datetime).total_seconds())

                    last_incoming_datetime = None
                    awaiting_reply = False

    if awaiting_reply:
        messages_without_reply = 1

    average_night_reply = sum(r_times_night) / len(r_times_night) if r_times_night else None
    average_working_reply = sum(r_times_working) / len(r_times_working) if r_times_working else None

    return {
        'typing_time': total_typing_symbols / typing_speed if typing_speed else 0,
        'reading_time': total_reading_words / reading_speed if reading_speed else 0,
        'incoming_messages': total_incoming_messages,
        'outgoing_messages': total_outgoing_messages,
        'incoming_symbols': total_incoming_symbols,
        'outgoing_symbols': total_outgoing_symbols,
        'average_working_reply': average_working_reply,
        'average_night_reply': average_night_reply,
        'messages_without_reply': messages_without_reply,
        'working_reply_times': r_times_working,
        'night_reply_times': r_times_night
    }


def format_time(total_minutes):
    total_seconds = int(total_minutes * 60)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60 if total_seconds % 60 > 0 else 1
    result = ""
    result += f"{hours}ч " if hours else ""
    result += f"{minutes}м " if minutes else ""
    result += f"{seconds}с"
    return result


def format_duration(total_seconds):
    total_seconds = int(total_seconds)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0 or days > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}м")
    parts.append(f"{seconds}с")
    return ' '.join(parts)


def write_chat_statistics(chat_stats_list, filename='chat_statistics.txt'):

    with open(filename, 'w', encoding='utf-8') as f:
        for stats in chat_stats_list:
            f.write(f"Чат с {stats['chat_name']}:\n")
            f.write(f"   Времени на печать: {stats['typing_time']}\n")
            f.write(f"   Времени на прочтение: {stats['reading_time']}\n")
            f.write(f"   Исходящие: {stats['total_outgoing_messages']}\n")
            f.write(f"   Входящие: {stats['total_incoming_messages']}\n")
            f.write(f"   Написано символов: {stats['total_outgoing_symbols']}\n")
            f.write(f"   Получено символов: {stats['total_incoming_symbols']}\n")
            f.write(f"   Среднее время ответа (рабочее время): {stats['work_reply_time']}\n")
            f.write(f"   Среднее время ответа (нерабочее время): {stats['night_reply_time']}\n")
            f.write(f"   Сообщений без ответа: {stats['messages_without_reply']}\n")
            f.write("\n")


async def fetch_messages(client, entity, start_date, end_date):
    # messages_by_date = defaultdict(list)

    messages = []

    async for message in client.iter_messages(entity, offset_date=end_date + timedelta(days=1)):
        if message.date.date() < start_date.date():
            break

        if start_date.date() <= message.date.date() <= end_date.date():
            messages.append(message)

    return messages


async def process_chats(client, start_date, end_date, work_start, work_end):
    me = await client.get_me()
    start_date = datetime(start_date.year, start_date.month, start_date.day)
    end_date = datetime(end_date.year, end_date.month, end_date.day)
    date_start_str = start_date.strftime('%Y-%m-%d')
    date_end_str = end_date.strftime('%Y-%m-%d')

    output_dir = f'{sanitize_folder_name(me.first_name)}_messages_{date_start_str}_{date_end_str}'
    os.makedirs(output_dir, exist_ok=True)

    total_typing_time = 0
    total_reading_time = 0
    total_incoming_messages = 0
    total_outgoing_messages = 0
    total_incoming_symbols = 0
    total_outgoing_symbols = 0
    total_work_reply_times = []
    total_night_reply_times = []
    total_messages_without_reply = 0

    chat_stats_list = []

    async for dialog in client.iter_dialogs(offset_date=datetime.now()):
        if dialog.date.date() < start_date.date():
            break

        entity = dialog.entity

        if isinstance(entity, User) and not entity.bot and entity.id != me.id and entity.id != 777000:
            messages = await fetch_messages(client, entity, start_date, end_date)

            if messages:
                user_name = f"{entity.first_name or ''}_{entity.last_name or ''}_{entity.id}"
                user_name = user_name.strip().replace(' ', '_').replace(os.sep, '_')
                user_dir = os.path.join(output_dir, sanitize_folder_name(user_name))
                os.makedirs(user_dir, exist_ok=True)
                print(f"Получаю чат с {entity.first_name} {entity.last_name or ''}")


                save_messages(user_dir, f'{sanitize_folder_name(user_name)}.txt', messages)

                stats = calculate_time_spent(messages, work_start, work_end)
                typing_time = stats['typing_time']
                reading_time = stats['reading_time']
                incoming_messages = stats['incoming_messages']
                outgoing_messages = stats['outgoing_messages']
                incoming_symbols = stats['incoming_symbols']
                outgoing_symbols = stats['outgoing_symbols']
                average_working_reply = stats['average_working_reply']
                average_night_reply = stats['average_night_reply']
                work_reply_times = stats['working_reply_times']
                night_reply_times = stats['night_reply_times']
                messages_without_reply = stats['messages_without_reply']

                average_working_reply_formatted = format_duration(average_working_reply) if average_working_reply else "N/A"
                average_night_reply_formatted = format_duration(average_night_reply) if average_night_reply else "N/A"

                # FOR TESTING PURPOSES
                # with open(os.path.join('chat_statistics_ny.txt'), 'a', encoding='utf-8') as f:
                #     f.write(f"Чат с {entity.first_name} {entity.last_name or ''}:\n")
                #     f.write(f"   Среднее время ответа (рабочее время): {average_working_reply_formatted}\n")
                #     f.write(f"   Среднее время ответа (нерабочее время): {average_night_reply_formatted}\n")
                #     f.write(f"   work_reply_times: {work_reply_times}\n")
                #     f.write(f"   night_reply_times: {night_reply_times}\n")
                #
                #     f.write("\n\n")

                # Accumulate for overall stats
                total_typing_time += typing_time
                total_reading_time += reading_time
                total_incoming_messages += incoming_messages
                total_outgoing_messages += outgoing_messages
                total_incoming_symbols += incoming_symbols
                total_outgoing_symbols += outgoing_symbols
                total_work_reply_times.extend(work_reply_times)
                total_night_reply_times.extend(night_reply_times)
                total_messages_without_reply += messages_without_reply

                # Prepare chat statistics for writing to file
                chat_stats = {
                    'chat_name': f"{entity.first_name} {entity.last_name or ''}".strip(),
                    'typing_time': format_time(typing_time),
                    'reading_time': format_time(reading_time),
                    'total_incoming_messages': incoming_messages,
                    'total_outgoing_messages': outgoing_messages,
                    'total_incoming_symbols': incoming_symbols,
                    'total_outgoing_symbols': outgoing_symbols,
                    'work_reply_time': average_working_reply_formatted,
                    'night_reply_time': average_night_reply_formatted,
                    'messages_without_reply': messages_without_reply
                }

                chat_stats_list.append(chat_stats)

                if messages_without_reply > 0:
                    unanswered_dir = os.path.join(output_dir, '!!!!!UNANSWERED')
                    os.makedirs(unanswered_dir, exist_ok=True)
                    dest_chat_dir = os.path.join(unanswered_dir, sanitize_folder_name(user_name))
                    # Copy the entire chat directory
                    shutil.copytree(user_dir, dest_chat_dir, dirs_exist_ok=True)

    write_chat_statistics(chat_stats_list, filename=f'{sanitize_folder_name(me.first_name)}_statistics_{date_start_str}_{date_end_str}.txt')

    if total_work_reply_times:
        overall_work_reply_time = sum(total_work_reply_times) / len(total_work_reply_times)
        overall_work_reply_time_formatted = format_duration(overall_work_reply_time)
    else:
        overall_work_reply_time_formatted = "N/A"

    if total_night_reply_times:
        overall_night_reply_time = sum(total_night_reply_times) / len(total_night_reply_times)
        overall_night_reply_time_formatted = format_duration(overall_night_reply_time)
    else:
        overall_night_reply_time_formatted = "N/A"

    print("\n=== Общая статистика ===")
    print(f"Всего времени на печать: {format_time(total_typing_time)}")
    print(f"Всего времени на прочтение: {format_time(total_reading_time)}")
    print(f"Исходящих сообщений: {total_outgoing_messages}")
    print(f"Входящих сообщений: {total_incoming_messages}")
    print(f"Написано символов: {total_outgoing_symbols}")
    print(f"Получено символов: {total_incoming_symbols}")
    print(f"Среднее время ответа в рабочее время (по всех чатах): {overall_work_reply_time_formatted}")
    print(f"Среднее время ответа в нерабочее время (по всех чатах): {overall_night_reply_time_formatted}")
    print(f"Сообщений без ответа: {total_messages_without_reply}")

