from supabase import create_client
import logging
from config import Config

logger = logging.getLogger(__name__)

class SupabaseDB:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

        self._client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("✅ Supabase client initialized successfully")

    def get_client(self):
        return self._client

    def fetch_one(self, table: str, filters: dict = None, columns: str = "*"):
        query = self._client.table(table).select(columns)
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        result = query.execute()
        return result.data[0] if result.data else None

    def fetch_all(self, table: str, filters: dict = None, columns: str = "*"):
        query = self._client.table(table).select(columns)
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        result = query.execute()
        return result.data

    def insert(self, table: str, data: dict):
        result = self._client.table(table).insert(data).execute()
        return result.data[0] if result.data else None

    def update(self, table: str, data: dict, filters: dict):
        query = self._client.table(table).update(data)
        for key, value in filters.items():
            query = query.eq(key, value)
        result = query.execute()
        return result.data[0] if result.data else None

    def delete(self, table: str, filters: dict):
        query = self._client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        result = query.execute()
        return result.data

# Singleton instance
db = SupabaseDB()
