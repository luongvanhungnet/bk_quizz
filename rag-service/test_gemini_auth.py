import sys
import importlib.metadata

from google import genai


print("Python:", sys.executable)
print("google-genai:", importlib.metadata.version("google-genai"))

client = genai.Client()

print("\nListing models...")

models = list(client.models.list())

for model in models:
    if "3.6-flash" in model.name:
        print("Found:", model.name)

print("\nGenerating...")

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="Reply exactly with OK",
)

print("Response:", response.text)