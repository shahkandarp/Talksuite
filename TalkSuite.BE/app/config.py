from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://talksuite_admin:password@localhost:5432/talksuite"

    # AWS Bedrock
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-6"
    bedrock_knowledge_base_id: str = ""

    # NetSuite accounts are now stored in the DB (multi-account).
    # These per-account fields are no longer used at the app level.

    # JWT Auth
    jwt_secret: str = "talksuite-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # App
    app_env: str = "development"
    debug: bool = False
    frontend_url: str = ""

    # Agent loop — max reasoning↔tool iterations before giving up
    agent_max_iterations: int = 15

    # Encryption (for secrets at rest — client secrets, refresh tokens)
    encryption_key: str = "talksuite-dev-default-key-change-me"

    # PKCE redirect base — where NetSuite redirects after login.
    # The callback path /accounts/pkce/callback is appended.
    pkce_redirect_base: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
