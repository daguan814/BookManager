from dataclasses import dataclass
import os


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "Lhf134652")
    db_name: str = os.getenv("DB_NAME", "bookmanager")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8081"))
    # Use app-specific SSL env names to avoid clashing with OpenSSL globals.
    ssl_cert_file: str | None = _optional_env("APP_SSL_CERT_FILE")
    ssl_key_file: str | None = _optional_env("APP_SSL_KEY_FILE")
    app_secret_key: str = os.getenv("APP_SECRET_KEY", "bookmanager-change-this-secret")
    web_login_password: str = os.getenv("WEB_LOGIN_PASSWORD", "sgxx")
    script_api_token: str = os.getenv("SCRIPT_API_TOKEN", "bookmanager-script-token")
    session_days: int = int(os.getenv("SESSION_DAYS", "7"))
    db_connect_retries: int = int(os.getenv("DB_CONNECT_RETRIES", "20"))
    db_connect_retry_delay: float = float(os.getenv("DB_CONNECT_RETRY_DELAY", "3"))
    shumaidata_appid: str = "xZT0HZmiaFg2rWbEWS3ODE3u26sCmhmk"
    shumaidata_app_security: str = "FNlCyjyL2JndvhluQEk59gUcEI8GG3va"

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()
