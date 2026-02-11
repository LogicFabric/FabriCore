# server/app/services/orchestrator.py
from app.services.data_manager import DataManager
from app.services.communication_manager import CommunicationManager
from app.models.protocol import JSONRPCRequest, JSONRPCResponse, AgentIdentifyParams
import logging
import json

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, data_manager: DataManager, comm_manager: CommunicationManager):
        self.db = data_manager
        self.comm = comm_manager

    async def handle_agent_message(self, agent_id: str, message: dict):
        try:
            # Basic JSON-RPC handling
            if "method" in message:
                await self.handle_request(agent_id, message)
            elif "result" in message or "error" in message:
                await self.handle_response(agent_id, message)
            else:
                logger.warning(f"Unknown message format from {agent_id}: {message}")
        except Exception as e:
            logger.error(f"Error handling message from {agent_id}: {e}")

    async def handle_request(self, agent_id: str, message: dict):
        method = message.get("method")
        params = message.get("params")
        msg_id = message.get("id")

        if method == "agent.identify":
            await self.handle_identify(agent_id, params)
        else:
            logger.info(f"Received request {method} from {agent_id}")

    async def handle_response(self, agent_id: str, message: dict):
        logger.info(f"Received response from {agent_id}: {message}")
        # TODO: Match with pending requests if we were tracking them

    async def handle_identify(self, connection_id: str, params: dict):
        # In a real scenario, params would be validated against AgentIdentifyParams
        # For now, just register
        agent_id = params.get("agent_id")
        logger.info(f"Agent identified as {agent_id}")
        
        # Register in DB
        self.db.register_agent({
            "id": agent_id,
            "hostname": params.get("os_info", {}).get("hostname"),
            "platform": params.get("os_info", {}).get("platform"),
            "status": "online",
            "capabilities": params.get("capabilities"),
            "os_info": params.get("os_info")
        })
        
        # We might need to map connection_id (ws) to agent_id if they differ
        # but CommunicationManager handles ws object directly, so maybe we update key?
        # For simplicity, assuming connection logic handles the mapping or re-mapping.
