from functools import lru_cache
from typing import Generator
from app.services.data_manager import DataManager
from app.services.agent_manager import AgentManager

@lru_cache()
def get_data_manager() -> DataManager:
    return DataManager()

@lru_cache()
def get_agent_manager() -> AgentManager:
    return AgentManager()

def get_db():
    dm = get_data_manager()
    db = dm.SessionLocal()
    try:
        yield db
    finally:
        db.close()
