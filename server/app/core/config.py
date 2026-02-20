from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "FabriCore"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str
    DB_PASSWORD: str = ""
    MODEL_PATH: str = "./llm_models/llama-2-7b.gguf"

    # Web Push / VAPID
    VAPID_PRIVATE_KEY_PATH: str = "/server/private_key.pem"
    VAPID_PUBLIC_KEY: str = "BOaWubIZS55BVFjq6paMnETmsnJYZjue-X-Bi57AOQ69JuVCcpH-xKZ3k0b8nSxxvmsq-mSSGJaLLHY0RrawEjc"
    VAPID_CLAIMS_EMAIL: str = "mailto:admin@fabricore.local"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
