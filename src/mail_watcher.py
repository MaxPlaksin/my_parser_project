import imaplib
import email
import os
import re
import logging
from datetime import datetime
import time
import threading
import importlib
from email.header import decode_header
import pandas as pd

# === НАСТРОЙКИ ===
EMAIL = 'almazgeobur.it@mail.ru'
PASSWORD = 'K7cAiTCjvVn50YiHqdnp'
IMAP_SERVER = 'imap.mail.ru'
CHECK_INTERVAL_SECONDS = 600  # 10 минут между проверками
MAILBOX = 'INBOX'
EXCEL_FILENAME = 'для бота.xlsx'  # Фиксированное имя для сохранения
TARGET_SUBJECTS = ['Остатки бот от', '1С УТ']  # Ключевые слова в теме письма

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mail_watcher.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def decode_mail_header(header):
    """Декодирует заголовки писем"""
    decoded = decode_header(header)
    return ''.join(
        str(t[0], t[1] or 'utf-8') if isinstance(t[0], bytes) else str(t[0])
        for t in decoded
    )


def is_target_email(msg):
    """Проверяет, является ли письмо целевым"""
    subject = decode_mail_header(msg.get('Subject', ''))
    from_email = msg.get('From', '')

    # Проверяем по теме письма
    is_target_subject = any(keyword in subject for keyword in TARGET_SUBJECTS)

    # Дополнительная проверка для писем от 1С УТ
    is_1c_ut = ('1С УТ' in subject) and ('almazgeobur.it@mail.ru' in from_email)

    return is_target_subject or is_1c_ut


def download_latest_excel():
    """Скачивает последний Excel-файл из целевого письма"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select(MAILBOX)

        # Ищем все письма, сортируем от новых к старым
        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            logger.warning("Не удалось выполнить поиск писем")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            logger.info("Нет писем в ящике")
            return False

        # Перебираем письма от новых к старым
        for msg_id in message_ids[::-1]:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            # Пропускаем письма, которые не соответствуют критериям
            if not is_target_email(msg):
                continue

            logger.info(f"Обработка письма: {decode_mail_header(msg.get('Subject', ''))}")

            # Поиск вложений
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                filename = decode_mail_header(filename)
                if not filename.lower().endswith('.xlsx'):
                    continue

                # Сохраняем файл
                file_content = part.get_payload(decode=True)
                with open(EXCEL_FILENAME, 'wb') as f:
                    f.write(file_content)

                logger.info(f"Файл {filename} сохранен как {EXCEL_FILENAME}")
                return True

        logger.info("Не найдено подходящих писем с Excel-файлами")
        return False

    except Exception as e:
        logger.error(f"Ошибка при проверке почты: {e}")
        return False
    finally:
        try:
            mail.logout()
        except:
            pass


def reload_main_module():
    """Перезагружает основной модуль с новой базой"""
    try:
        import main
        importlib.reload(main)
        main.df = main.load_database()
        logger.info(f"База перезагружена, записей: {len(main.df)}")
        return True
    except Exception as ex:
        logger.error(f"Ошибка при перезагрузке: {ex}")
        return False


def run_scheduled_check():
    """Запускает периодическую проверку почты"""

    def loop():
        while True:
            logger.info("Проверка новых писем...")
            if download_latest_excel():
                reload_main_module()
            time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


if __name__ == '__main__':
    run_scheduled_check()
    while True:
        time.sleep(60)