import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # JWT
    JWT_SECRET = os.getenv("JWT_SECRET", "fallback-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "flask-secret-change-me")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"
    
    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5000,http://localhost:3000").split(",")
    
    # Admin
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Trading Engine
    TRADE_WINDOW_DURATION_SECONDS = int(os.getenv("TRADE_WINDOW_DURATION_SECONDS", "3"))
    TRADE_WINDOW_INTERVAL_SECONDS = int(os.getenv("TRADE_WINDOW_INTERVAL_SECONDS", "60"))
    PRICE_UPDATE_INTERVAL_MS = int(os.getenv("PRICE_UPDATE_INTERVAL_MS", "500"))
    
    # Payment
    PROFIT_PERCENTAGE = int(os.getenv("PROFIT_PERCENTAGE", "80"))
    
    # Other
    DEFAULT_BALANCE = 10000.00
    MIN_TRADE_AMOUNT = 10
    MAX_TRADE_AMOUNT = 100000
    
    # Test mode (for bypassing time restrictions)
    TEST_OFFSET_HOURS = int(os.getenv("TEST_OFFSET_HOURS", "0"))