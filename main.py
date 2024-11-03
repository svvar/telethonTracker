from datetime import datetime

import os
import json
import re
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

import stats_tracker

CONFIG_PATH = 'stored_sessions/sessions.json'


def load_sessions():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({"sessions": {}}, f, indent=4)
    with open(CONFIG_PATH, 'r') as f:
        data = json.load(f)
    return data.get('sessions', {})


def save_sessions(sessions):
    with open(CONFIG_PATH, 'w') as f:
        json.dump({"sessions": sessions}, f, indent=4)


def add_session_to_config(session_id, api_id, api_hash, phone):
    sessions = load_sessions()
    sessions[session_id] = {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone
    }
    save_sessions(sessions)
    print(f"Акаунт '{session_id}' добавлен")


def remove_session_from_config(session_id):
    sessions = load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        save_sessions(sessions)
        print(f"Акаунт '{session_id}' удален.")
    else:
        print(f"Акаунт '{session_id}' не найден.")


def ensure_session_directory(directory='stored_sessions'):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Создана папка: {directory}")


def sanitize_phone(phone):
    sanitized = re.sub(r'[^\d+]', '', phone)
    return sanitized


def list_sessions(directory='stored_sessions'):
    sessions = []
    for file in os.listdir(directory):
        if file.endswith('.session'):
            session_name = os.path.splitext(file)[0]
            sessions.append(session_name)
    return sessions

def display_menu():
    print("\n=== Анализатор статистики чатов ===")
    print("1. Выбрать из ранее добавленых")
    print("2. Добавить новый акаунт")
    print("3. Удалить акаунт")
    print("4. Выход")
    choice = input("Выберите действие (1-4): ").strip()
    return choice


async def login(session_file, api_id, api_hash, phone):
    try:
        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input('Введите код который вы получили: ').strip()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input('Двухфакторная авторизация. Введите пароль: ')
                await client.sign_in(password=password)
        print("Успех!")
        me = await client.get_me()
        print(f'Акаунт: {me.first_name} ({me.username})')

        await client.disconnect()

        return client

    except Exception as e:
        print(f"Ошибка во время входа: {e}")
        if os.path.exists(session_file):
            os.remove(session_file)
    finally:
        await client.disconnect()


async def add_new_session(directory='stored_sessions'):
    phone = input("\nВведите номер телефона (полный, напр.: +380991234567): ").strip()
    session_file = os.path.join(directory, f"{sanitize_phone(phone)}.session")

    api_id = input("Введите Telegram API ID: ").strip()
    api_hash = input("Введите Telegram API Hash: ").strip()

    if not api_id.isdigit():
        print("Неверный API ID. Пожалуйста, введите целое число.")
        return

    session = await login(session_file, int(api_id), api_hash, phone)

    if session:
        add_session_to_config(sanitize_phone(phone), api_id, api_hash, phone)
        await dump_menu(session)


def remove_existing_session(directory='stored_sessions'):
    sessions = list_sessions(directory)
    if not sessions:
        print("\nСписок пуст")
        return

    print("\n=== Удаление акаунта ===")
    for idx, session in enumerate(sessions, start=1):
        print(f"{idx}. {session}")

    try:
        choice = int(input("Выберите акаунт по номеру телефона: ").strip())
        if 1 <= choice <= len(sessions):
            session_id = sessions[choice - 1]
            session_file = os.path.join(directory, f"{session_id}.session")

            if os.path.exists(session_file):
                os.remove(session_file)

            remove_session_from_config(session_id)
        else:
            print("Неверный выбор. Пожалуйста, выберите существующий акаунт.")
    except ValueError:
        print("Неверный выбор. Пожалуйста, выберите существующий акаунт.")


async def select_from_saved_sessions():
    sessions = list_sessions()
    if not sessions:
        print("\nСписок пуст")
        return

    print("\n=== Выбор акаунта ===")
    for idx, session in enumerate(sessions, start=1):
        print(f"{idx}.  {session}")

    session_menu_selector = f"1-{len(sessions)}" if len(sessions) >= 2 else "1"
    try:
        choice = int(input(f"Выберите акаунт ({session_menu_selector}): ").strip())
        if 1 <= choice <= len(sessions):
            session_id = sessions[choice - 1]
            session_file = os.path.join('stored_sessions', f"{session_id}.session")

            config_loaded = load_sessions()
            api_id = config_loaded[session_id]['api_id']
            api_hash = config_loaded[session_id]['api_hash']

            session = TelegramClient(session_file, api_id, api_hash)
            await dump_menu(session)
        else:
            print("Неверный выбор. Пожалуйста, выберите существующий акаунт.")
    except ValueError:
        print("Неверный выбор. Пожалуйста, выберите существующий акаунт.")


# =======================
# Dump menu
# =======================


async def dump_menu(session):
    print("\n=== Получение статистики ===")

    while True:
        date_input = input("Введите дату по которой нужно получить статистику (ДД.ММ.ГГГГ)\n"
                           "или диапазон дат (ДД.ММ.ГГГГ - ДД.ММ.ГГГГ): ")
        try:
            if '-' not in date_input:
                date_start = date_end = datetime.strptime(date_input, "%d.%m.%Y").date()
            else:
                date_start, date_end = date_input.split('-')
                date_start = datetime.strptime(date_start.strip(), "%d.%m.%Y").date()
                date_end = datetime.strptime(date_end.strip(), "%d.%m.%Y").date()
        except ValueError:
            print("Неверный формат даты. Повторите")
        else:
            break

    async with session:
        await stats_tracker.process_chats(session, date_start, date_end)


# =======================
# Main Loop
# =======================

async def main():
    ensure_session_directory()

    while True:
        choice = display_menu()
        os.system('cls')

        if choice == '1':
            await select_from_saved_sessions()

        elif choice == '2':
            await add_new_session()

        elif choice == '3':
            remove_existing_session()

        elif choice == '4':
            break

        else:
            print("Неизвестный выбор. Повторите.")


asyncio.run(main())