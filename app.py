import os
import streamlit as st

if "GOOGLE_API_KEY" in st.secrets:
    os.environ["GOOGLE_API_KEY"] = st.secrets["GOOGLE_API_KEY"]

from agent import create_finance_agent

# Налаштування сторінки
st.set_page_config(page_title="MoneyWise Web", page_icon="💰", layout="centered")

# Ініціалізація стану (щоб пам'ять не зникала при оновленні сторінки)
if "agent" not in st.session_state:
    st.session_state.agent = create_finance_agent()
if "messages" not in st.session_state:
    st.session_state.messages = []

# Бічна панель (вимоги до UI-компонентів з домашки)
with st.sidebar:
    st.header("⚙️ Налаштування")
    st.info("Модель: Gemini 2.5 Flash")
    
    if st.button("🗑️ Очистити історію", use_container_width=True):
        st.session_state.agent = create_finance_agent() # Створюємо агента з чистою пам'яттю
        st.session_state.messages = []
        st.rerun()
        
    st.divider()
    
    # Використання st.expander() та st.metric()
    with st.expander("🛠️ Доступні інструменти"):
        st.markdown("- Калькулятор кредитів\n- Оптимізатор бюджету\n- Конвертер валют\n- Пошук DuckDuckGo")
        
    st.metric("Повідомлень у чаті", len(st.session_state.messages))

# Основний заголовок
st.title("💰 MoneyWise: Фінансовий Асистент")

# Відображення історії чату
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Поле вводу та обробка повідомлення
if prompt := st.chat_input("Спитайте про фінанси, кредити чи валюту..."):
    # Додаємо запит юзера в інтерфейс
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Звертаємося до нашого агента
    with st.chat_message("assistant"):
        with st.spinner("Аналізую фінанси..."):
            try:
                # Викликаємо агента з файлу agent.py
                response = st.session_state.agent.run(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Детальна помилка: {e}")