# server/app/api/routers.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse
from app.services.data_manager import DataManager
from app.api.v1 import websocket
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency Injection (Simple version for now)
# In a real app, use overrides or a DI container
# Include sub-routers
router.include_router(websocket.router, prefix="/api/v1")

@router.get("/api/v1/agents")
async def list_agents():
    db = data_manager.get_db()
    try:
        from app.models.db import Agent
        agents = db.query(Agent).all()
        return agents
    finally:
        db.close()
