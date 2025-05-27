import imaplib
import email
from email.header import decode_header
import os
import zipfile
import logging
import time
import threading
import sys

# === НАСТРОЙКИ ===
EMAIL = 'almazgeobur.it@mail.ru'
PASSWORD = 'K7cAiTCjvVn50YiHqdnp'
IMAP_SERVER = 'imap.mail.ru'
SAVE_ZIP_PATH = 'latest_baza.zip'
HTML_OUTPUT_PATH = 'для бота (HTML4).html'
SENDER_FILTER = '1c@almazgeobur.kz'
SUBJECT_KEYWORD = 'Остатки бот'
CHECK_INTERVAL_MINUTES = 60  # проверка каждый час

# Настройка логгирования с обработкой ошибок кодировки
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("mail_watcher.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
except Exception as e:
    # Запасной вариант без указания кодировки
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("mail_watcher.log"),
            logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)


# Безопасная функция логгирования
def safe_log(level, message):
    try:
        if level == 'info':
            logger.info(message)
        elif level == 'error':
            logger.error(message)
        elif level == 'warning':
            logger.warning(message)
    except Exception as e:
        # Если не удалось залогировать с эмодзи или спец. символами
        try:
            # Попытка залогировать без спец. символов
            clean_message = ''.join(c for c in message if ord(c) < 128)
            if level == 'info':
                logger.info(clean_message)
            elif level == 'error':
                logger.error(clean_message)
            elif level == 'warning':
                logger.warning(clean_message)
        except:
            # Если всё ещё не работает, используем print
            print(f"{level.upper()}: Не удалось залогировать сообщение")


def download_and_extract_latest_zip():
    try:
        safe_log('info', "Подключение к почтовому ящику...")

        if os.path.basename(__file__) == 'imaplib.py':
            safe_log('error', "Конфликт имён: переименуйте текущий скрипт, он не должен называться 'imaplib.py'")
            return False

        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select('inbox')

        safe_log('info', "Поиск письма с темой 'Остатки бот' от отправителя '1c@almazgeobur.kz'")

        # Используем простой поиск без кириллицы
        status, messages = mail.search(None, f'FROM "{SENDER_FILTER}"')
        if status != 'OK':
            safe_log('warning', "Письма не найдены.")
            return False

        message_ids = messages[0].split()
        if not message_ids:
            safe_log('warning', "Нет писем по заданному фильтру.")
            return False

        # Проверяем письма в обратном порядке (от новых к старым)
        for msg_id in reversed(message_ids):
            try:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Проверяем тему письма
                subject = msg.get('Subject', '')
                try:
                    # Пытаемся декодировать заголовок
                    subject_parts = decode_header(subject)
                    subject = ''
                    for part, encoding in subject_parts:
                        if isinstance(part, bytes):
                            # Пробуем разные кодировки
                            for enc in [encoding, 'utf-8', 'latin1', 'cp1251']:
                                if enc is None:
                                    continue
                                try:
                                    subject += part.decode(enc)
                                    break
                                except:
                                    continue
                        else:
                            subject += str(part)
                except:
                    # Если не удалось декодировать, используем как есть
                    pass

                # Если тема не содержит ключевое слово, пропускаем
                if SUBJECT_KEYWORD.lower() not in subject.lower():
                    continue

                # Нашли подходящее письмо, ищем вложения
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue

                    # Получаем имя файла
                    try:
                        filename = part.get_filename()
                        if filename:
                            # Пытаемся декодировать имя файла
                            filename_parts = decode_header(filename)
                            filename = ''
                            for part_name, encoding in filename_parts:
                                if isinstance(part_name, bytes):
                                    # Пробуем разные кодировки
                                    for enc in [encoding, 'utf-8', 'latin1', 'cp1251']:
                                        if enc is None:
                                            continue
                                        try:
                                            filename += part_name.decode(enc)
                                            break
                                        except:
                                            continue
                                else:
                                    filename += str(part_name)
                    except:
                        # Если не удалось декодировать, генерируем имя
                        filename = f"attachment_{msg_id.decode('ascii')}.zip"

                    # Если это ZIP-файл, сохраняем его
                    if filename and filename.lower().endswith('.zip'):
                        try:
                            with open(SAVE_ZIP_PATH, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            safe_log('info', f"ZIP-файл сохранён: {SAVE_ZIP_PATH}")

                            # Пытаемся извлечь HTML-файл из архива
                            try:
                                with zipfile.ZipFile(SAVE_ZIP_PATH, 'r') as zip_ref:
                                    html_found = False
                                    for zip_info in zip_ref.infolist():
                                        try:
                                            # Проверяем, является ли файл HTML
                                            if zip_info.filename.lower().endswith(
                                                    '.html') or zip_info.filename.lower().endswith('.htm'):
                                                # Извлекаем с новым именем
                                                zip_info.filename = HTML_OUTPUT_PATH
                                                zip_ref.extract(zip_info, '.')
                                                safe_log('info', f"HTML-файл извлечён: {HTML_OUTPUT_PATH}")
                                                html_found = True
                                                return True
                                        except Exception as e:
                                            safe_log('error', f"Ошибка при извлечении файла из архива: {str(e)}")
                                            continue

                                    if not html_found:
                                        safe_log('warning', "ZIP найден, но HTML внутри не обнаружен.")
                            except Exception as e:
                                safe_log('error', f"Ошибка при работе с ZIP-архивом: {str(e)}")
                        except Exception as e:
                            safe_log('error', f"Ошибка при сохранении ZIP-файла: {str(e)}")
            except Exception as e:
                safe_log('error', f"Ошибка при обработке письма: {str(e)}")
                continue

        safe_log('warning', "Не найдено подходящих писем с вложениями.")
        return False

    except Exception as e:
        # Безопасное логгирование ошибки
        try:
            error_message = str(e)
            safe_log('error', f"Ошибка при обработке почты: {error_message}")
        except:
            print("ERROR: Не удалось залогировать ошибку")
        return False


def run_scheduled_check():
    def loop():
        while True:
            try:
                safe_log('info', "Запускаю проверку наличия новой базы...")
                success = download_and_extract_latest_zip()
                if success:
                    safe_log('info', "Новая база обновлена.")
                else:
                    safe_log('info', "Новых обновлений не найдено.")
            except Exception as e:
                try:
                    safe_log('error', f"Ошибка в цикле проверки: {str(e)}")
                except:
                    print("ERROR: Ошибка в цикле проверки")

            # Ждем следующей проверки
            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


if __name__ == '__main__':
    run_scheduled_check()
    while True:
        time.sleep(60)  # бесконечный цикл, чтобы держать поток активным
