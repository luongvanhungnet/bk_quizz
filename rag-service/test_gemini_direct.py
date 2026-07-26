from app.core.config import get_settings
from google import genai

settings = get_settings()

key = settings.gemini_api_key
if hasattr(key, "get_secret_value"):
    key = key.get_secret_value()

model = settings.gemini_model

print("Model configured:", model)
print("Key configured:", bool(key))
print("Key length:", len(key or ""))

client = genai.Client(api_key=key)

print("\nChecking accessible models...")
model_names = []

for item in client.models.list():
    name = getattr(item, "name", "")
    model_names.append(name)

for target in ("gemini-3.5-flash", "gemini-2.5-flash"):
    found = any(target in name for name in model_names)
    print(f"{target}: available={found}")

print("\nTesting configured model...")
response = client.models.generate_content(
    model=model,
    contents="Trả lời chính xác một từ: OK",
)

print("Response:", response.text)
client.close()
