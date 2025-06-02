import imaplib
import email
import os
import logging
import shutil
import tempfile
from email.header import decode_header
import pandas as pd
import time
import threading
import importlib
from contextlib import contextmanager

# === НАСТРОЙКИ ===
EMAIL = 'almazgeobur.it@mail.ru'
PASSWORD = 'K7cAiTCjvVn50YiHqdnp'
IMAP_SERVER = 'imap.mail.ru'
CHECK_INTERVAL_SECONDS = 600  # 10 минут между проверками
MAILBOX = 'INBOX'
EXCEL_FILENAME = 'для бота.xlsx'
TARGET_SUBJECTS = ['Остатки бот от', '1С УТ']

# Настройка логгера
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
    if header is None:
        return ""
    decoded = decode_header(header)
    return ''.join(
        str(t[0], t[1] or 'utf-8') if isinstance(t[0], bytes) else str(t[0])
        for t in decoded
    )


def is_target_email(msg):
    """Проверяет, является ли письмо целевым"""
    subject = decode_mail_header(msg.get('Subject', ''))
    from_email = msg.get('From', '')
    return any(keyword in subject for keyword in TARGET_SUBJECTS)


@contextmanager
def atomic_file_replace(filename):
    """Контекстный менеджер для атомарной замены файла"""
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_{os.path.basename(filename)}")
    backup_path = os.path.join(temp_dir, f"backup_{os.path.basename(filename)}")

    try:
        if os.path.exists(filename):
            shutil.copy2(filename, backup_path)

        yield temp_path

        if os.path.exists(temp_path):
            if os.path.exists(filename):
                os.unlink(filename)
            shutil.move(temp_path, filename)

    except Exception as e:
        logger.error(f"Ошибка при замене файла: {e}")
        if os.path.exists(backup_path) and not os.path.exists(filename):
            shutil.copy2(backup_path, filename)
        raise
    finally:
        for path in [temp_path, backup_path]:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass


def download_latest_excel():
    """Скачивает последний Excel-файл из целевого письма"""
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select(MAILBOX)

        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            logger.warning("Не удалось выполнить поиск писем")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            logger.info("Нет писем в ящике")
            return False

        for msg_id in message_ids[::-1]:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            if not is_target_email(msg):
                continue

            logger.info(f"Обработка письма: {decode_mail_header(msg.get('Subject', ''))}")

            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                filename = decode_mail_header(filename)
                if not filename.lower().endswith('.xlsx'):
                    continue

                try:
                    with atomic_file_replace(EXCEL_FILENAME) as temp_file:
                        with open(temp_file, 'wb') as f:
                            f.write(part.get_payload(decode=True))

                    logger.info(f"Файл {filename} успешно сохранен как {EXCEL_FILENAME}")
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при сохранении файла: {e}")
                    continue

        logger.info("Не найдено подходящих писем с Excel-файлами")
        return False

    except imaplib.IMAP4.error as e:
        logger.error(f"Ошибка IMAP: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return False
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass


def reload_main_module():
    """Перезагружает основной модуль с новой базой"""
    try:
        import main
        importlib.reload(main)
        main.df = main.load_database()
        logger.info(f"База перезагружена, записей: {len(main.df)}")
        return True
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}")
        return False
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
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")