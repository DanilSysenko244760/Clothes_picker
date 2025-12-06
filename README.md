# Clothes_picker
An intelligent Telegram bot that helps you find coordinated fashion outfits using AI-powered search and style matching.

## Features

-  **AI-Powered Coordination**: Uses Claude 3.5 Sonnet to analyze and coordinate outfits
-  **Smart Search**: Integrates with Google Shopping via SerpAPI
-  **Style Matching**: Automatically matches items by style, color, and price range
-  **Budget Control**: Respects your budget constraints
-  **Brand Support**: Understands specific brands and styles (Acne Studios, Balenciaga, etc.)
-  **Complete Outfits**: Creates full coordinated looks with multiple items

## How It Works

1. **Analysis**: Understands your request and extracts details (categories, brands, budget)
2. **Search**: Searches for items that match your criteria
3. **Coordination**: AI analyzes each item for style, color, and price compatibility
4. **Selection**: Chooses items that work together harmoniously

## Example Queries
"outfit with acne studios hoodie and opium style sneakers under $1000"
"find balenciaga look"
"streetwear outfit with t-shirt"
"gothic black sneakers"

## Setup

### Prerequisites

- Python 3.8+
- Telegram Bot Token ([BotFather](https://t.me/BotFather))
- OpenRouter API Key ([OpenRouter](https://openrouter.ai/settings/credits))
- SerpAPI Key ([SerpAPI](https://serpapi.com/))

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/fashion-ai-bot.git
cd fashion-ai-bot
```

2. Create virtual environment:
```bash
python -m venv venv
```

3. Activate virtual environment:
- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` with your API keys:
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_key
SERPAPI_KEY=your_serpapi_key
AI_MODEL=anthropic/claude-3.5-sonnet

6. Run the bot:
```bash
python main.py
```

## Bot Commands

- `/start` - Start the bot and see welcome message
- `/help` - Get help on how to use the bot

## Configuration

### AI Model Options

- `anthropic/claude-3.5-sonnet` (recommended, balanced)
- `anthropic/claude-3-opus` (highest quality, more expensive)
- `anthropic/claude-3-haiku` (fastest, cheapest)
- 'you can choose your own on openrouter`
  
## API Costs

Approximate costs per outfit search:
- OpenRouter (Claude): ~$0.01-0.05 per outfit
- SerpAPI: ~$0.01-0.03 per outfit
- Total: ~$0.02-0.08 per complete outfit

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Support

For issues and questions, please open an issue on GitHub.

---

Made with ❤️
