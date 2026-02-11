# server/app/api/routers.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse
from app.services.communication_manager import CommunicationManager
from app.services.orchestrator import Orchestrator
from app.services.data_manager import DataManager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency Injection (Simple version for now)
# In a real app, use overrides or a DI container
data_manager = DataManager()
comm_manager = CommunicationManager()
orchestrator = Orchestrator(data_manager, comm_manager)

@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    # In a real app, validate token here
    agent_id = "unknown" # Will be set during Identify handshake
    await comm_manager.connect(websocket, agent_id)
    try:
        while True:
            data = await websocket.receive_json()
            # If identify, update agent_id in comm_manager mapping if needed
            # For now, orchestrator handles the message
            await orchestrator.handle_agent_message(agent_id, data)
            
            # If agent_id is still unknown, try to extract it from identify message
            if agent_id == "unknown" and data.get("method") == "agent.identify":
                 agent_id = data.get("params", {}).get("agent_id", "unknown")
                 # We should ideally update the key in comm_manager, but for this simple impl
                 # we might just rely on the connection being open. 
                 # To do it properly:
                 comm_manager.active_connections[agent_id] = comm_manager.active_connections.pop("unknown", websocket)

    except WebSocketDisconnect:
        comm_manager.disconnect(agent_id)
        # Update status to offline
        data_manager.update_agent_status(agent_id, "offline")

@router.get("/api/v1/agents")
async def list_agents():
    db = data_manager.get_db()
    try:
        from app.models.db import Agent
        agents = db.query(Agent).all()
        return agents
    finally:
        db.close()
