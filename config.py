from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "Lhf134652")
    db_name: str = os.getenv("DB_NAME", "bookmanager")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "18080"))
    ssl_cert_file: str | None = os.getenv("SSL_CERT_FILE", "/etc/nginx/ssl/shuijing.site.pem")
    ssl_key_file: str | None = os.getenv("SSL_KEY_FILE", "/etc/nginx/ssl/shuijing.site.key")
    shumaidata_appid: str = "xZT0HZmiaFg2rWbEWS3ODE3u26sCmhmk"
    shumaidata_app_security: str = "FNlCyjyL2JndvhluQEk59gUcEI8GG3va"

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()
