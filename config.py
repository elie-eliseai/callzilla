import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    
    # Server Configuration
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Disclaimer Configuration
    TARGET_DISCLAIMER = os.getenv('TARGET_DISCLAIMER', '')
    
    # Call Configuration
    HUMAN_MESSAGE = (
        "This is EliseAI. "
        "We will call again, please let it go to voicemail."
    )
    
    # File paths
    CSV_FILE = 'properties.csv'
    RESULTS_FILE = 'call_results.csv'
    
    @staticmethod
    def validate():
        """Validate required configuration"""
        required = [
            'TWILIO_ACCOUNT_SID',
            'TWILIO_AUTH_TOKEN',
            'TWILIO_PHONE_NUMBER',
            'OPENAI_API_KEY'
        ]
        missing = [key for key in required if not getattr(Config, key)]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

