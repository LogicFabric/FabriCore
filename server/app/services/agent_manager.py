from typing import Dict, Any
from fastapi import WebSocket
import json
import logging
from app.models.agent import AgentCreate

logger = logging.getLogger(__name__)

class AgentManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_info: Dict[str, AgentCreate] = {}

    async def register_connection(self, agent_id: str, websocket: WebSocket, agent_data: AgentCreate):
        """
        Registers an active WebSocket connection and agent metadata.
        The WebSocket should already be accepted by the endpoint.
        """
        self.active_connections[agent_id] = websocket
        self.agent_info[agent_id] = agent_data
        logger.info(f"Agent {agent_id} registered and connected.")

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
        # In a real app we might want to keep the info but mark as offline
        # For now, we update status if we kept it, or just remove for simple in-memory listing
        if agent_id in self.agent_info:
            self.agent_info[agent_id].status = "offline"
        logger.info(f"Agent {agent_id} disconnected.")

    def get_agent(self, agent_id: str) -> AgentCreate:
        return self.agent_info.get(agent_id)

    async def send_command(self, agent_id: str, command: Dict[str, Any], db = None):
        """
        Sends a command to the agent and logs it to the DB if a session is provided.
        """
        if agent_id in self.active_connections:
            websocket = self.active_connections[agent_id]
            
            # Wrap in JSON-RPC Request
            # We need a unique ID for the request
            import uuid
            request_id = str(uuid.uuid4())
            
            json_rpc_request = {
                "jsonrpc": "2.0",
                "method": "tool.execute", # Generic method for tool execution
                "params": {
                    "tool_name": command.get("tool_name"),
                    "arguments": command.get("arguments", {})
                },
                "id": request_id
            }
            
            # Save to Audit Log if DB session is available
            if db:
                from app.models.audit_log import AuditLog
                audit_entry = AuditLog(
                    id=request_id,
                    agent_id=agent_id,
                    tool_name=command.get("tool_name"),
                    arguments=command.get("arguments", {}),
                    status="pending"
                )
                db.add(audit_entry)
                db.commit()
            
            await websocket.send_text(json.dumps(json_rpc_request))
            logger.info(f"Command sent to agent {agent_id}: {json_rpc_request}")
            return request_id
        else:
            logger.warning(f"Agent {agent_id} not connected.")
            return None

agent_manager = AgentManager()
