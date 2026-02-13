from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
# Pydantic Schemas for Agent Communication

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
