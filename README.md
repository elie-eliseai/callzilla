# EliseAI Detection System

Automated system to detect if apartment properties use EliseAI for their leasing communication.

## Overview

This system:
1. Scrapes phone numbers from multiple sources (Google, Apartments.com, property websites)
2. Makes automated calls to property leasing lines
3. Navigates phone trees to reach voicemail
4. Analyzes recordings to detect EliseAI vs human vs other AI

## Project Structure

```
Voice_Automation/
├── simple_production_caller.py  # Main orchestration script
├── scraper/                     # Phone scraping package
│   ├── scraper.py              # Main scraper logic
│   ├── google.py               # Google search scraping
│   ├── apartments.py           # Apartments.com scraping  
│   ├── property_website.py     # Property website scraping
│   ├── clients.py              # API clients (SerpAPI, Bright Data, OpenAI)
│   └── ...
├── gpt_analysis.py             # GPT-based call classification
├── twiml_generator.py          # Twilio TwiML generation
├── csv_utils.py                # CSV loading utilities
└── logging_utils.py            # Logging utilities
```

## Setup

1. Copy `.env.example` to `.env` and fill in credentials:
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
   - `OPENAI_API_KEY`
   - `SERPAPI_KEY`
   - `BRIGHTDATA_TOKEN`, `BRIGHTDATA_ZONE`

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start ngrok for webhooks:
   ```bash
   ngrok http 5000
   ```

4. Update `BASE_URL` in `.env` with ngrok URL

## Usage

### Scrape phone numbers only
```bash
python3 simple_production_caller.py properties.csv --scrape-only
```

### Call scraped numbers
```bash
python3 simple_production_caller.py scraped_phones.csv --call-only
```

### Full pipeline (scrape + call)
```bash
python3 simple_production_caller.py properties.csv
```

## Input CSV Format

```csv
property_name,location
The Heights,Austin, TX
Sunset Apartments,Denver, CO
```

## Requirements

- Python 3.9+
- Twilio account
- OpenAI API key
- SerpAPI key
- Bright Data Web Unlocker account
- ngrok (for webhooks)
