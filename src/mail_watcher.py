import imaplib
import email
import os
import zipfile
import logging
from datetime import datetime
import time
import threading
import importlib

# === НАСТРОЙКИ ===
EMAIL = 'almazgeobur.it@mail.ru'
PASSWORD = 'K7cAiTCjvVn50YiHqdnp'
IMAP_SERVER = 'imap.mail.ru'
SAVE_ZIP_PATH = 'latest_baza.zip'
EXCEL_OUTPUT_PATH = 'Остатки2.xlsx'
SENDER_FILTER = '1c@almazgeobur.kz'
CHECK_INTERVAL_MINUTES = 60

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def download_and_extract_latest_zip():
    try:
        logger.info("📬 Подключение к почтовому ящику...")

        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select('inbox')

        logger.info("🔎 Поиск последнего письма от '1c@almazgeobur.kz' с вложением .xlsx")
        status, messages = mail.search(None, f'FROM "{SENDER_FILTER}"')
        if status != 'OK':
            logger.warning("❌ Письма не найдены.")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            logger.warning("📭 Нет писем от заданного отправителя.")
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

            # Получаем имя файла и декодируем его, если необходимо
            filename = part.get_filename()
            if not filename:
                continue

            # Обработка кодировки имени файла
            try:
                if isinstance(filename, bytes):
                    filename = filename.decode('utf-8', errors='replace')
            except Exception as e:
                logger.warning(f"Ошибка декодирования имени файла: {e}")

            logger.info(f"Найдено вложение: {filename}")

            # Обработка Excel-файла
            if filename.lower().endswith('.xlsx'):
                with open(EXCEL_OUTPUT_PATH, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                logger.info(f"📄 Excel-файл сохранён как: {EXCEL_OUTPUT_PATH}")
                return True

            # Обработка ZIP-архива
            elif filename.lower().endswith('.zip'):
                with open(SAVE_ZIP_PATH, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                logger.info(f"📦 ZIP-файл сохранён: {SAVE_ZIP_PATH}")

                try:
                    with zipfile.ZipFile(SAVE_ZIP_PATH, 'r') as zip_ref:
                        excel_found = False
                        for zip_info in zip_ref.infolist():
                            zip_filename = zip_info.filename
                            # Обработка кодировки имени файла в архиве
                            try:
                                if isinstance(zip_filename, bytes):
                                    zip_filename = zip_filename.decode('utf-8', errors='replace')
                            except Exception as e:
                                logger.warning(f"Ошибка декодирования имени файла в архиве: {e}")

                            if zip_filename.lower().endswith('.xlsx'):
                                # Переименовываем файл при извлечении
                                zip_info.filename = EXCEL_OUTPUT_PATH
                                zip_ref.extract(zip_info, '.')
                                logger.info(f"📄 Excel-файл извлечён из ZIP: {EXCEL_OUTPUT_PATH}")
                                excel_found = True
                                break

                        if not excel_found:
                            logger.warning("❗ Excel-файл не найден в ZIP-архиве.")
                            return False
                        return True
                except Exception as e:
                    logger.error(f"Ошибка при распаковке ZIP-архива: {e}")
                    return False

        logger.warning("❗ Подходящее вложение не найдено.")
        return False

    except Exception as e:
        error_message = str(e)
        # Обработка ошибок кодировки
        if isinstance(error_message, bytes):
            error_message = error_message.decode('utf-8', errors='replace')
        logger.error(f"Ошибка при обработке почты: {error_message}")
        return False


def run_scheduled_check():
    def loop():
        while True:
            logger.info("⏳ Запускаю проверку наличия новой базы...")
            success = download_and_extract_latest_zip()
            if success:
                logger.info("✅ Новая база обновлена. Перезагружаю данные...")
                try:
                    # Используем importlib для динамической перезагрузки модуля
                    import main
                    importlib.reload(main)
                    main.df = main.load_database()
                    logger.info(f"📦 Загружено {len(main.df)} записей из новой базы")
                except Exception as ex:
                    error_message = str(ex)
                    # Обработка ошибок кодировки
                    if isinstance(error_message, bytes):
                        error_message = error_message.decode('utf-8', errors='replace')
                    logger.error(f"Ошибка при перезагрузке базы в основном модуле: {error_message}")
            else:
                logger.info("🔁 Новых обновлений не найдено.")
            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


if __name__ == '__main__':
    run_scheduled_check()
    while True:
        time.sleep(60)  # бесконечный цикл, чтобы держать поток активным
