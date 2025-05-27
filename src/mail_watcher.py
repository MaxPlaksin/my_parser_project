import imaplib
import email
import os
import zipfile
import logging
from datetime import datetime
import time
import threading

# === НАСТРОЙКИ ===
EMAIL = 'almazgeobur.it@mail.ru'
PASSWORD = 'K7cAiTCjvVn50YiHqdnp'
IMAP_SERVER = 'imap.mail.ru'
SAVE_ZIP_PATH = 'latest_baza.zip'
HTML_OUTPUT_PATH = 'для бота (HTML4).html'
SENDER_FILTER = '1c@almazgeobur.kz'
SUBJECT_KEYWORD = 'Остатки бот'
CHECK_INTERVAL_MINUTES = 60  # проверка каждый час

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_and_extract_latest_zip():
    try:
        logger.info("📬 Подключение к почтовому ящику...")

        if os.path.basename(__file__) == 'imaplib.py':
            logger.error("Конфликт имён: переименуйте текущий скрипт, он не должен называться 'imaplib.py'")
            return False

        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select('inbox')

        logger.info("🔎 Поиск письма с темой 'Остатки бот' от отправителя '1c@almazgeobur.kz'")
        status, messages = mail.search(None, f'FROM "{SENDER_FILTER}" SUBJECT "{SUBJECT_KEYWORD}"')
        if status != 'OK':
            logger.warning("❌ Письма не найдены.")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            logger.warning("📭 Нет писем по заданному фильтру.")
            return False

        latest_id = message_ids[-1]
        status, msg_data = mail.fetch(latest_id, '(RFC822)')
        if status != 'OK':
            logger.error("Не удалось получить содержимое письма.")
            return False

        msg = email.message_from_bytes(msg_data[0][1])
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            filename = part.get_filename()
            if filename and filename.endswith('.zip'):
                with open(SAVE_ZIP_PATH, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                logger.info(f"📦 ZIP-файл сохранён: {SAVE_ZIP_PATH}")

                with zipfile.ZipFile(SAVE_ZIP_PATH, 'r') as zip_ref:
                    for zip_info in zip_ref.infolist():
                        if zip_info.filename.endswith('.html'):
                            zip_info.filename = HTML_OUTPUT_PATH
                            zip_ref.extract(zip_info, '.')
                            logger.info(f"📄 HTML-файл извлечён: {HTML_OUTPUT_PATH}")
                            return True
        logger.warning("❗ ZIP найден, но HTML внутри не обнаружен.")
        return False

    except Exception as e:
        logger.error(f"Ошибка при обработке почты: {e}")
        return False

def run_scheduled_check():
    def loop():
        while True:
            logger.info("⏳ Запускаю проверку наличия новой базы...")
            success = download_and_extract_latest_zip()
            if success:
                logger.info("✅ Новая база обновлена.")
            else:
                logger.info("🔁 Новых обновлений не найдено.")
            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

if __name__ == '__main__':
    run_scheduled_check()
    while True:
        time.sleep(60)  # бесконечный цикл, чтобы держать поток активным
