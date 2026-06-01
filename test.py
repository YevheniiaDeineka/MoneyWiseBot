import os
import google.generativeai as genai

# Встав свій ключ
os.environ["GOOGLE_API_KEY"] = "AIzaSyDZK1uEvfgpnxQzOJFwBre-TFKIIg3TdvA"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

print("Доступні моделі для твого ключа:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)