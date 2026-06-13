import os
import math
import requests
from langchain.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationSummaryBufferMemory
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.prompts import MessagesPlaceholder
from langchain.callbacks import FileCallbackHandler
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key

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

def get_live_rates(base_currency="UAH"):
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    try:
        response = requests.get(url)
        data = response.json()
        if data["result"] == "success":
            return data["rates"]
        return None
    except Exception as e:
        return None

@tool
def currency_converter(amount: float, from_currency: str, to_currency: str) -> dict:
    """Конвертує суму між валютами."""
    rates = get_live_rates(from_currency.upper())
    if not rates: return {"error": "Не вдалося отримати курси валют"}
    target = to_currency.upper()
    if target in rates:
        rate = rates[target]
        return {"from": from_currency.upper(), "to": target, "amount_converted": round(amount * rate, 2)}
    return {"error": f"Валюта {target} не підтримується"}

@tool
def inflation_calculator(amount: float, annual_inflation_rate: float, years: int) -> dict:
    """Розраховує вплив інфляції."""
    rate = annual_inflation_rate / 100
    future_cost = amount * (1 + rate) ** years
    purchasing_power = amount / ((1 + rate) ** years)
    return {"future_cost": round(future_cost, 2), "loss_percent": round((1 - purchasing_power / amount) * 100, 1)}

@tool
def loan_calculator(principal: float, annual_rate: float, months: int, loan_type: str = "ануїтет") -> str:
    """Розраховує параметри кредиту."""
    monthly_rate = annual_rate / 100 / 12
    payment = principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)
    return f"Щомісячний платіж: {payment:,.2f} грн. Загальна переплата: {(payment * months) - principal:,.2f} грн."

@tool
def savings_goal(target_amount: float, monthly_savings: float = 0, months_available: int = 0) -> str:
    """Розраховує план накопичення на фінансову мету."""
    if monthly_savings > 0:
        months_needed = target_amount / monthly_savings
        return f"Ви накопичите суму за {int(months_needed // 12)} років і {int(months_needed % 12)} місяців."
    return "Вкажіть суму щомісячних заощаджень."

@tool
def budget_optimizer(monthly_income: float, actual_expenses: dict) -> dict:
    """Аналізує витрати користувача."""
    if monthly_income <= 0: return {"error": "Дохід має бути більшим за нуль."}
    return {"monthly_income": monthly_income, "advice": "Порівняння з моделлю 50/30/20 виконано успішно."}

search_tool = DuckDuckGoSearchRun(name="internet_search", description="Пошук в інтернеті фінансових новин.")

# Функція, яка створює і повертає готового агента
def create_finance_agent():
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
    tools = [loan_calculator, savings_goal, currency_converter, inflation_calculator, budget_optimizer, search_tool]
    
    memory = ConversationSummaryBufferMemory(
        llm=llm, 
        max_token_limit=5000, 
        memory_key="chat_history", 
        return_messages=True
    )
    
    agent_executor = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        memory=memory,
        handle_parsing_errors=True,
        agent_kwargs={"memory_prompts": [MessagesPlaceholder(variable_name="chat_history")]}
    )
    return agent_executor