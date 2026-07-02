from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Invoice ERP"
    ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database — connects to existing PostgreSQL on VPS
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # Resend email
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str = "invoices@yourdomain.com"

    # File uploads — local disk on Hostinger
    UPLOAD_DIR: str = "/var/www/invoice_erp/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # In-app notifications
    NOTIFICATIONS_PAGE_SIZE: int = 20

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
