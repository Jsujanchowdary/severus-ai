import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from utils.ollama_client import chat_with_model
import metrics

print("Testing Ollama with DeepSeek...")
try:
    # Small test message
    response = chat_with_model(
        "deepseek-v3.1:671b-cloud",
        [("user", "Hello, are you DeepSeek?")],
        chat_id=999
    )
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {e}")
