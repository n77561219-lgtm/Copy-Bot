import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    telegram_allowed_users: str = ""

    # OpenRouter
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Models
    model_haiku: str = "anthropic/claude-3-5-haiku"
    model_sonnet: str = "anthropic/claude-3-5-sonnet"
    model_image: str = "google/gemini-2.5-flash-image"
    model_trends: str = "perplexity/sonar"

    # Apify
    apify_token: str = ""

    # ЮКасса
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    webhook_secret: str = ""
    bot_url: str = "https://t.me/Copy_plan_bot"
    webhook_port: int = 8080

    # Database
    database_url: str = "postgresql://copybot_user:copybot_pass_2026@localhost:5432/copybot"

    # Storage
    style_profiles_dir: str = "data/style_profiles"
    uploads_dir: str = "data/uploads"

    @property
    def allowed_user_ids(self) -> set[int]:
        if not self.telegram_allowed_users.strip():
            return set()
        return {
            int(uid.strip())
            for uid in self.telegram_allowed_users.split(",")
            if uid.strip().isdigit()
        }

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

os.makedirs(settings.style_profiles_dir, exist_ok=True)
os.makedirs(settings.uploads_dir, exist_ok=True)
