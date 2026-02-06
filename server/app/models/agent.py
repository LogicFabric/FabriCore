from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class AgentDB(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    status = Column(String, default="offline")
    last_seen = Column(DateTime, default=datetime.utcnow)
    platform = Column(String)
    hostname = Column(String)
    arch = Column(String)
    memory_total = Column(Integer)
    supported_tools = Column(JSON)

# Pydantic Schemas

class AgentBase(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None

class AgentCreate(AgentBase):
    id: str
    platform: str
    hostname: str
    arch: str
    memory_total: int
    supported_tools: List[str]

class Agent(AgentBase):
    id: str
    last_seen: datetime
    platform: Optional[str] = None
    hostname: Optional[str] = None
    arch: Optional[str] = None
    memory_total: Optional[int] = None
    supported_tools: Optional[List[str]] = None

    class Config:
        from_attributes = True
