# server/app/services/communication_manager.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)

class CommunicationManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        logger.info(f"Agent {agent_id} connected.")

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
            logger.info(f"Agent {agent_id} disconnected.")

    async def send_message(self, agent_id: str, message: dict):
        if agent_id in self.active_connections:
            await self.active_connections[agent_id].send_json(message)
        else:
            logger.warning(f"Attempted to send message to offline agent {agent_id}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)
