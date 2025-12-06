"""
Configuration file for Fashion AI Bot
Loads settings from environment variables
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in environment variables")

# SerpAPI Configuration
SERPAPI_KEY = os.getenv('SERPAPI_KEY')
if not SERPAPI_KEY:
    raise ValueError("SERPAPI_KEY not found in environment variables")

# AI Model Configuration
AI_MODEL = os.getenv('AI_MODEL', 'anthropic/claude-3.5-sonnet')
AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://openrouter.ai/api/v1')

# Validate configuration
def validate_config():
    """Validate that all required configuration is present"""
    required_vars = {
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'OPENROUTER_API_KEY': OPENROUTER_API_KEY,
        'SERPAPI_KEY': SERPAPI_KEY
    }
    
    missing = [key for key, value in required_vars.items() if not value]
    
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please check your .env file"
        )
    
    print("✓ Configuration validated successfully")
    print(f"✓ Using AI model: {AI_MODEL}")

if __name__ == "__main__":
    validate_config()
