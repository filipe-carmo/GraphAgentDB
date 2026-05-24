import os
import json
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).parent.resolve()

class Settings(BaseSettings):
    gemini_api_key: Optional[str] = None
    conflict_similarity_threshold: float = 0.88
    gemini_model: str = "gemini-2.5-flash"
    embed_model: str = "text-embedding-004"
    embed_dim: int = 768
    kuzu_db_path: str = "kuzu_db.db"
    lancedb_path: str = "vector_index_lance"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

# Instantiate settings and load config.json configuration
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        # Load from .env if present
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=BACKEND_DIR.parent / ".env")
        
        # Base setup
        config_data = {}
        config_path = BACKEND_DIR / "config.json"
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"[Settings Warning] Failed to parse config.json: {e}")
        
        # Override with env variables or standard settings constructor
        _settings = Settings(
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            **config_data
        )
        
        # Resolve DB paths to absolute pathing relative to backend dir
        _settings.kuzu_db_path = str((BACKEND_DIR / _settings.kuzu_db_path).resolve())
        _settings.lancedb_path = str((BACKEND_DIR / _settings.lancedb_path).resolve())
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(_settings.kuzu_db_path), exist_ok=True)
        os.makedirs(_settings.lancedb_path, exist_ok=True)
        
    return _settings

# Default settings instance for easy importing
settings = get_settings()
