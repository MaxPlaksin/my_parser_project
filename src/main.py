import telebot
import requests
import pandas as pd

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7136103155:AAHS8y4z7CsdSpddDddU6p60TM8dTFElXmY'       # ← Telegram токен
PROTALK_BOT_TOKEN = 'DqyF1zh55CU3qzp8QUo8cblDD4ckh2b6'                   # ← Pro Talk токен (из меню API)
PROTALK_BOT_ID = 26395                                                  # ← Pro Talk bot_id (уточни свой!)

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)



# === Загрузка Excel-файла (опционально, если нужно использовать базу) ===
print("📂 Загружаю Excel-файл...")
df = pd.read_excel('Остатки (1).xlsx', sheet_name='TDSheet')
df = df.dropna(subset=['Номенклатура', 'Артикул'])

# === Отправка запроса в Pro Talk ===
def ask_protalk(text, chat_id='telegram_user'):
    url = f'https://api.pro-talk.ru/api/v1.0/ask/{PROTALK_BOT_TOKEN}'
    headers = {'Content-Type': 'application/json'}
    payload = {
        "bot_id": PROTALK_BOT_ID,
        "chat_id": chat_id,
        "message": text
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("done", "Нет ответа от нейросети.")
    except Exception as e:
        return f"❌ Ошибка при запросе к Pro Talk: {e}"

# === Обработка сообщений Telegram ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    bot.send_chat_action(message.chat.id, 'typing')
    reply = ask_protalk(user_text, chat_id=str(message.chat.id))
    bot.reply_to(message, reply)

# === Запуск ===
print("✅ Бот запущен и ждёт запросов...")
bot.polling()
