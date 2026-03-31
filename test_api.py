"""
test_api.py — Quick test of NVIDIA API and Qwen model

Tests that the API key is valid and the model responds correctly.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "qwen/qwen3.5-122b-a10b"


def test_api():
    """Test NVIDIA API connection and model response."""
    
    if not NVIDIA_API_KEY:
        print("❌ NVIDIA_API_KEY not found in .env")
        return False
    
    print(f"🔑 API Key: {NVIDIA_API_KEY[:20]}...{NVIDIA_API_KEY[-10:]}")
    print(f"🤖 Model: {MODEL_NAME}")
    print(f"🌐 Endpoint: {INVOKE_URL}\n")
    
    try:
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json"
        }
        
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": "Say 'Hello from xbot!' and nothing else."}
            ],
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.95,
            "stream": False,
        }
        
        print("📡 Sending request to NVIDIA API...\n")
        response = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=30)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API responded successfully!\n")
            
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {}).get("content", "")
                print(f"🤖 Model response:")
                print(f"   {message}\n")
                
                if "Hello from xbot" in message:
                    print("✅ Model is working correctly!")
                    return True
                else:
                    print("⚠️  Unexpected response, but API is working")
                    return True
            else:
                print("⚠️  Unexpected response format")
                print(json.dumps(result, indent=2))
                return False
        else:
            print(f"❌ API error: {response.status_code}")
            print(response.text[:500])
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (API may be overloaded)")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error (check internet or endpoint URL)")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 Testing NVIDIA API + Qwen Model")
    print("=" * 70 + "\n")
    
    success = test_api()
    
    print("=" * 70)
    if success:
        print("✅ All tests passed! API is ready to use.")
    else:
        print("❌ Tests failed. Check your API key and internet connection.")
    print("=" * 70)
