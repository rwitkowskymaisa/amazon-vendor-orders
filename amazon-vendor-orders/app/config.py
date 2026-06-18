from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    amazon_client_id: str = ""
    amazon_client_secret: str = ""
    amazon_refresh_token: str = ""
    amazon_vendor_code: str = "BRVND"
    secret_key: str = "dev-secret-change-in-production"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings():
    return Settings()
