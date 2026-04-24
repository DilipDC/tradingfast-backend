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
    
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "flask-secret-change-me")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"
    
    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://tradingfast-frontend.vercel.app").split(",")
    
    # Admin
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Trading Engine
    TRADE_WINDOW_DURATION_SECONDS = int(os.getenv("TRADE_WINDOW_DURATION_SECONDS", "3"))
    TRADE_WINDOW_INTERVAL_SECONDS = int(os.getenv("TRADE_WINDOW_INTERVAL_SECONDS", "60"))
    PRICE_UPDATE_INTERVAL_MS = int(os.getenv("PRICE_UPDATE_INTERVAL_MS", "500"))
    
    # Defaults
    DEFAULT_BALANCE = 10000.00
    MIN_TRADE_AMOUNT = 10
