import os
import telebot
import threading
from flask import Flask
from agent import create_finance_agent # Імпортуємо нашого агента!

telegram_token = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(telegram_token)

# Створюємо агента для бота
telegram_agent = create_finance_agent()

print("🤖 MoneyWise Telegram Bot запущено...")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привіт! Я MoneyWise — твій фінансовий AI-асистент. Напиши мені своє питання!")

@bot.message_handler(func=lambda message: True)
def chat_with_agent(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        response = telegram_agent.run(message.text)
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, "Вибач, я трохи заплутався в розрахунках.")

# Flask-сервер для підтримки Render
app = Flask(__name__)

@app.route('/')
def home():
    return "MoneyWise TG Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def run_bot():
    bot.infinity_polling(none_stop=True, skip_pending=True)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    threading.Thread(target=run_bot).start()