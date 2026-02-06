from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "FabriCore"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str = "postgresql://fabricore:securepassword@localhost:5432/fabricore"
    MODEL_PATH: str = "./llm_models/llama-2-7b.gguf"

    class Config:
        env_file = ".env"

settings = Settings()
