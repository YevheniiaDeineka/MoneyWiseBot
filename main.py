import os
import math
import requests
from langchain.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain.memory import (
    ConversationBufferMemory,
    ConversationBufferWindowMemory, 
    ConversationSummaryMemory, 
    ConversationSummaryBufferMemory
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.prompts import MessagesPlaceholder
from langchain.callbacks import FileCallbackHandler
import telebot
from dotenv import load_dotenv
import threading
from flask import Flask

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")

os.environ["GOOGLE_API_KEY"] = google_api_key

# Ініціалізуємо стабільну, швидку і безкоштовну модель Google Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1
)

# Рекомендований розподіл бюджету (правило 50/30/20)
BUDGET_NORMS = {
    "житло": {"min": 0.20, "max": 0.30, "рекомендовано": 0.25},
    "їжа": {"min": 0.10, "max": 0.15, "рекомендовано": 0.12},
    "транспорт": {"min": 0.05, "max": 0.15, "рекомендовано": 0.10},
    "комунальні": {"min": 0.05, "max": 0.10, "рекомендовано": 0.07},
    "здоров'я": {"min": 0.03, "max": 0.10, "рекомендовано": 0.05},
    "розваги": {"min": 0.05, "max": 0.10, "рекомендовано": 0.08},
    "одяг": {"min": 0.03, "max": 0.07, "рекомендовано": 0.05},
    "заощадження": {"min": 0.10, "max": 0.20, "рекомендовано": 0.15},
}

# --- ІНСТРУМЕНТИ (TOOLS) ---

#Функція, що отримує актуальні курси валют
def get_live_rates(base_currency="UAH"):
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    try:
        response = requests.get(url)
        data = response.json()
        if data["result"] == "success":
            return data["rates"]
        return None
    except Exception as e:
        print(f"Помилка API: {e}")
        return None

@tool
def currency_converter(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Конвертує суму між валютами. Повертає результат розрахунку та курс.
    """
    rates = get_live_rates(from_currency.upper())
    
    if not rates:
        return {"error": "Не вдалося отримати курси валют"}
    
    target = to_currency.upper()
    if target in rates:
        rate = rates[target]
        return {
            "from": from_currency.upper(),
            "to": target,
            "amount_original": amount,
            "amount_converted": round(amount * rate, 2),
            "rate": round(rate, 4)
        }
    else:
        return {"error": f"Валюта {target} не підтримується"}

@tool
def inflation_calculator(amount: float, annual_inflation_rate: float, years: int) -> dict:
    """Розраховує вплив інфляції. Повертає словник з розрахунками."""
    rate = annual_inflation_rate / 100
    future_cost = amount * (1 + rate) ** years
    purchasing_power = amount / ((1 + rate) ** years)
    
    # Повертаємо просто цифри
    return {
        "initial_amount": amount,
        "years": years,
        "future_cost": round(future_cost, 2),
        "purchasing_power": round(purchasing_power, 2),
        "loss_percent": round((1 - purchasing_power / amount) * 100, 1)
    }

@tool
def loan_calculator(principal: float, annual_rate: float, months: int, loan_type: str = "ануїтет") -> str:
    """
    Розраховує параметри кредиту: щомісячний платіж, переплату, графік.
    Використовуй цей інструмент для питань про кредити, іпотеку та щомісячні платежі.
    """
    if principal <= 0 or months <= 0:
        return "Помилка: Сума кредиту та термін (місяці) мають бути більшими за нуль."
    if annual_rate < 0:
        return "Помилка: Відсоткова ставка не може бути від'ємною."
    
    monthly_rate = annual_rate / 100 / 12
    
    if loan_type.lower() == "ануїтет":
        if monthly_rate == 0:
            payment = principal / months
        else:
            payment = principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)
        
        total = payment * months
        overpayment = total - principal
        
        # Формуємо міні-графік (перші 3 місяці)
        balance = principal
        schedule_start = []
        for i in range(min(3, months)):
            interest_part = balance * monthly_rate
            principal_part = payment - interest_part
            balance -= principal_part
            schedule_start.append(f" Місяць {i+1}: {payment:.2f} грн (тіло: {principal_part:.2f}, %: {interest_part:.2f})")
            
        return f"""💰 Розрахунок кредиту (ануїтет)
Сума кредиту: {principal:,.0f} грн
Ставка: {annual_rate}% річних
Термін: {months} місяців ({months/12:.1f} років)
📊 Результати:
- Щомісячний платіж: {payment:,.2f} грн
- Загальна сума виплат: {total:,.2f} грн
- Переплата за відсотками: {overpayment:,.2f} грн ({overpayment/principal*100:.1f}%)
📅 Початок графіка платежів:
{chr(10).join(schedule_start)}
...
⚠️ Це інформаційний розрахунок. Реальні умови можуть відрізнятися."""

    else:
        # Диференційований платіж
        principal_payment = principal / months
        total = 0
        max_payment = principal_payment + principal * monthly_rate
        min_payment = principal_payment + principal_payment * monthly_rate
        
        for i in range(months):
            remaining = principal - (principal_payment * i)
            interest = remaining * monthly_rate
            total += principal_payment + interest
            
        overpayment = total - principal
        return f"""💰 Розрахунок кредиту (диференційований)
Сума кредиту: {principal:,.0f} грн
Ставка: {annual_rate}% річних
Термін: {months} місяців
📊 Результати:
- Перший платіж (максимальний): {max_payment:,.2f} грн
- Останній платіж (мінімальний): {min_payment:,.2f} грн
- Загальна сума виплат: {total:,.2f} грн
- Переплата: {overpayment:,.2f} грн ({overpayment/principal*100:.1f}%)"""

@tool
def savings_goal(target_amount: float, monthly_savings: float = 0, months_available: int = 0, annual_return: float = 0) -> str:
    """
    Розраховує план накопичення на фінансову мету (за терміном або сумою внеску).
    """
    monthly_return = annual_return / 100 / 12 if annual_return > 0 else 0
    
    if monthly_savings > 0 and months_available == 0:
        # Розраховуємо термін
        if monthly_return == 0:
            months_needed = target_amount / monthly_savings
        else:
            months_needed = math.log(1 + target_amount * monthly_return / monthly_savings) / math.log(1 + monthly_return)
        
        years = int(months_needed // 12)
        remaining_months = int(months_needed % 12)
        total_invested = monthly_savings * months_needed
        interest_earned = target_amount - total_invested if monthly_return > 0 else 0
        
        return f"""🎯 План накопичення
Мета: {target_amount:,.0f} грн
Щомісячний внесок: {monthly_savings:,.0f} грн
{"Очікувана дохідність: " + str(annual_return) + "% річних" if annual_return > 0 else "Без урахування дохідності"}
📅 Результат:
Ви накопичите цільову суму за: {years} років {remaining_months} місяців
Загалом внесете: {total_invested:,.0f} грн
{"Дохід від інвестицій: " + f"{interest_earned:,.0f} грн" if interest_earned > 0 else ""}
💡 Порада: регулярність важливіша за суму."""

    elif months_available > 0:
        # Розраховуємо необхідний внесок
        if monthly_return == 0:
            required_monthly = target_amount / months_available
        else:
            required_monthly = target_amount * monthly_return / ((1 + monthly_return)**months_available - 1)
            
        return f"""🎯 План накопичення
Мета: {target_amount:,.0f} грн
Бажаний термін: {months_available} місяців ({months_available/12:.1f} років)
{"Очікувана дохідність: " + str(annual_return) + "% річних" if annual_return > 0 else ""}
💵 Необхідний щомісячний внесок: {required_monthly:,.2f} грн
Це {required_monthly/target_amount*100:.1f}% від цільової суми щомісяця."""
    
    else:
        return "Вкажіть або суму щомісячних заощаджень, або бажаний термін накопичення."
    
@tool
def compare_loans(principal: float, offers: list) -> dict:
    """
    Порівнює кілька кредитних пропозицій.
    'offers' має бути списком словників з ключами 'rate' (ставка) та 'months' (термін).
    """
    comparison_results = []
    
    for offer in offers:
        rate = offer.get("rate")
        months = offer.get("months")
        monthly_rate = rate / 100 / 12
        
        # Розрахунок ануїтету
        if monthly_rate == 0:
            payment = principal / months
        else:
            payment = principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)
        
        total_payout = payment * months
        overpayment = total_payout - principal
        
        comparison_results.append({
            "rate": rate,
            "months": months,
            "monthly_payment": round(payment, 2),
            "total_payout": round(total_payout, 2),
            "overpayment": round(overpayment, 2),
            "overpayment_percent": round((overpayment / principal) * 100, 1)
        })
    
    return {
        "principal": principal,
        "comparison": comparison_results
    }

@tool
def budget_optimizer(monthly_income: float, actual_expenses: dict) -> dict:
    """
    Аналізує витрати користувача порівняно з рекомендованими нормами.
    actual_expenses — словник витрат, наприклад: їжа: 5000, житло: 8000
    """

    if monthly_income <= 0:
        return {"error": "Дохід має бути більшим за нуль для розрахунку бюджету."}
    
    analysis = {}
    
    for category, amounts in BUDGET_NORMS.items():
        actual = actual_expenses.get(category, 0)
        percent_of_income = actual / monthly_income
        
        # Перевірка на перевищення ліміту
        if percent_of_income > amounts["max"]:
            diff_percent = (percent_of_income - amounts["max"]) * 100
            analysis[category] = {
                "status": "over_budget",
                "actual_percent": round(percent_of_income * 100, 1),
                "recommended_max": round(amounts["max"] * 100, 1),
                "excess_percent": round(diff_percent, 1)
            }
        elif actual == 0 and category == "заощадження":
            analysis[category] = {"status": "missing", "message": "Ви зовсім не відкладаєте гроші!"}
        else:
            analysis[category] = {"status": "ok", "actual_percent": round(percent_of_income * 100, 1)}

    return {
        "monthly_income": monthly_income,
        "category_analysis": analysis,
        "advice_logic": "Порівняння з моделлю 50/30/20"
    }

# Створюємо інструмент пошуку
search_tool = DuckDuckGoSearchRun(
    name="internet_search",
    description="Корисно, коли потрібно знайти актуальну або історичну інформацію в інтернеті, наприклад, рівень інфляції, економічні новини тощо."
)

# Список інструментів для LangChain агента
tools = [
    loan_calculator, 
    savings_goal, 
    currency_converter, 
    inflation_calculator, 
    compare_loans,
    budget_optimizer,
    search_tool
]

# 1. Налаштовуємо пам'ять
memory = ConversationSummaryBufferMemory(
    llm=llm, # Передаємо модель для стиснення старих повідомлень
    max_token_limit=500, # Ліміт токенів перед тим, як зробити конспект
    memory_key="chat_history",
    return_messages=True
)

# Створюємо обробник, який записуватиме всі події у файл
logfile_handler = FileCallbackHandler("MoneyWise_logs.log")
# 2. Ініціалізуємо агента
agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,                # Залишаємо логування в консоль
    memory=memory,
    handle_parsing_errors=True,
    agent_kwargs={
        "memory_prompts": [MessagesPlaceholder(variable_name="chat_history")]
    },
    callbacks=[logfile_handler]
)

# Ініціалізуємо Telegram-бота
bot = telebot.TeleBot(telegram_token)

print("🤖 MoneyWise Telegram Bot запущено...")

# Обробник команди /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привіт! Я MoneyWise — твій фінансовий AI-асистент. Напиши мені своє питання!")

# Обробник команди /memory (наша секретна фіча)
@bot.message_handler(commands=['memory'])
def show_memory(message):
    memory_data = memory.load_memory_variables({})
    bot.reply_to(message, f"🧠 [ДІАГНОСТИКА ПАМ'ЯТІ]\n\n{memory_data}")

# Обробник усіх інших текстових повідомлень
@bot.message_handler(func=lambda message: True)
def chat_with_agent(message):
    user_id = message.chat.id
    user_text = message.text
    
    # Відправляємо повідомлення "Бот друкує..."
    bot.send_chat_action(user_id, 'typing')
    
    try:
        # Передаємо текст від юзера нашому агенту LangChain
        response = agent_executor.run(user_text)
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, "Вибач, я трохи заплутався в розрахунках. Спробуй переформулювати запит.")
        print(f"Помилка: {e}")

# --- Мікро-вебсервер для хмарного хостингу (Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "MoneyWise Bot is running!"

def run_web():
    # Render автоматично видасть порт, або використаємо 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Запускаємо вебсервер у паралельному потоці, щоб він не блокував бота
threading.Thread(target=run_web).start()

# Запускаємо бота в режимі постійного очікування повідомлень
bot.infinity_polling()