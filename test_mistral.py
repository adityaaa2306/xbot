"""
Quick test to verify Mistral Large 3 API is working
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "mistralai/mistral-large-3-675b-instruct-2512"

if not NVIDIA_API_KEY:
    print("❌ Error: NVIDIA_API_KEY not found in .env")
    exit(1)

print(f"🧪 Testing Mistral Large 3 Model")
print(f"Model: {MODEL_NAME}")
print(f"API Key: {NVIDIA_API_KEY[:20]}...")
print()

headers = {
    "Authorization": f"Bearer {NVIDIA_API_KEY}",
    "Accept": "application/json"
}

payload = {
    "model": MODEL_NAME,
    "messages": [{"role": "user", "content": "Say 'Hello from autobot!' in exactly those words."}],
    "max_tokens": 2048,
    "temperature": 0.15,
    "top_p": 1.00,
    "frequency_penalty": 0.00,
    "presence_penalty": 0.00,
    "stream": False
}

print("📤 Sending request to NVIDIA API...")
try:
    response = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=30)
    
    print(f"\n✅ Response Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n📝 API Response:")
        print(json.dumps(result, indent=2))
        
        if result.get("choices"):
            message = result["choices"][0]["message"]["content"]
            print(f"\n🤖 Model Output:")
            print(f"   {message}")
        else:
            print("⚠️  No choices in response")
    else:
        print(f"❌ Error: {response.text}")
        
except requests.Timeout:
    print("❌ Request timed out (API may be unresponsive)")
except requests.RequestException as e:
    print(f"❌ Request failed: {str(e)}")
except Exception as e:
    print(f"❌ Error: {str(e)}")
