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

    # Used to build public links (e.g. the clarification-response link emailed
    # to an external respondent) that point back at the deployed frontend.
    FRONTEND_URL: str = "http://localhost:3000"

    # File uploads — local disk on Hostinger
    UPLOAD_DIR: str = "/var/www/invoice_erp/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # In-app notifications
    NOTIFICATIONS_PAGE_SIZE: int = 20

    # Pending-approval reminder digest (app/core/scheduler.py) — nothing else
    # notifies an approver when a request first lands in their queue, only on
    # the final decision, so a backlog can otherwise sit unnoticed.
    PENDING_REMINDER_THRESHOLD: int = 15
    # When set, reminder emails go here instead of the real approver — set
    # this in an environment while testing so real approvers aren't emailed;
    # leave unset for the real recipient to receive it.
    PENDING_REMINDER_TEST_EMAIL: str | None = None

    # JWT auth — short-lived access token, longer-lived refresh token that
    # exchanges for a new access token via POST /auth/refresh.
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    class Config:
        env_file = (
            ".env.development",
            ".env.staging",
            ".env.production",
            ".env",
        )
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
