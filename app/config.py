from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'sqlite:///./cst.db'
    secret_key: str = ''
    admin_password: str = ''
    cookie_secure: bool = False
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1-mini'
    math_question_count: int = 24
    logic_question_count: int = 20
    correct_answer_cooldown_days: int = Field(default=7, ge=1, le=365)


settings = Settings()
