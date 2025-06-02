import imaplib
import email
import os
import logging
from datetime import datetime, timedelta
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
ALLOWED_SENDERS = ['almazgeobur.it@mail.ru']
EXCEL_DIRECTORY = 'downloaded_files'
TARGET_EXCEL_NAME = 'для бота.xlsx'  # Имя файла, которое будет использоваться

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mail_watcher.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def setup_environment():
    """Создает необходимые директории"""
    if not os.path.exists(EXCEL_DIRECTORY):
        os.makedirs(EXCEL_DIRECTORY)


def clean_filename(filename):
    """Очищает имя файла от недопустимых символов"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def is_valid_excel(filepath):
    """Проверяет валидность Excel-файла"""
    try:
        pd.read_excel(filepath, nrows=1)
        return True
    except Exception as e:
        logger.error(f"Файл не является валидным Excel: {e}")
        return False


def download_latest_excel():
    """Скачивает последний Excel-файл из почты"""
    try:
        setup_environment()
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)

        # Выбираем почтовый ящик
        status, _ = mail.select(MAILBOX)
        if status != 'OK':
            logger.error("Не удалось выбрать почтовый ящик")
            return False

        # Ищем все письма (отсортированные по дате, новые первыми)
        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            logger.warning("Не удалось выполнить поиск писем")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            logger.info("Нет писем в ящике")
            return False

        # Берем самое последнее письмо (первое в списке)
        latest_msg_id = message_ids[0]

        status, msg_data = mail.fetch(latest_msg_id, '(RFC822)')
        if status != 'OK':
            logger.warning("Не удалось получить письмо")
            return False

        msg = email.message_from_bytes(msg_data[0][1])
        sender = email.utils.parseaddr(msg.get('From', ''))[1]

        # Проверяем отправителя
        if ALLOWED_SENDERS and sender not in ALLOWED_SENDERS:
            logger.warning(f"Письмо от недоверенного отправителя: {sender}")
            return False

        # Ищем вложения
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue

            filename = part.get_filename()
            if not filename:
                continue

            # Декодируем имя файла
            decoded_filename = decode_header(filename)
            filename = ''.join(
                str(t[0], t[1] or 'utf-8') if isinstance(t[0], bytes) else str(t[0])
                for t in decoded_filename
            )

            # Очищаем имя файла
            filename = clean_filename(filename)

            if not filename.lower().endswith('.xlsx'):
                continue

            try:
                file_content = part.get_payload(decode=True)
                temp_path = os.path.join(EXCEL_DIRECTORY, 'temp_' + filename)
                final_path = os.path.join(EXCEL_DIRECTORY, TARGET_EXCEL_NAME)

                # Сохраняем временный файл
                with open(temp_path, 'wb') as f:
                    f.write(file_content)

                # Проверяем валидность
                if is_valid_excel(temp_path):
                    # Удаляем старый файл, если существует
                    if os.path.exists(final_path):
                        os.remove(final_path)

                    # Переименовываем временный файл в целевое имя
                    os.rename(temp_path, final_path)
                    logger.info(f"Файл успешно сохранен как: {TARGET_EXCEL_NAME}")
                    return True
                else:
                    os.remove(temp_path)
                    logger.warning("Файл не прошел проверку валидности")

            except Exception as e:
                logger.error(f"Ошибка обработки файла: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False

        logger.info("В письме не найдено подходящего Excel-файла")
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
            logger.info("Проверка нового письма...")
            if download_latest_excel():
                reload_main_module()
            time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


if __name__ == '__main__':
    run_scheduled_check()
    while True:
        time.sleep(60)