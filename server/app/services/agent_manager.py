import json
import logging
import asyncio
import uuid
from typing import Dict, Any, Optional
from app.models.agent import AgentCreate

logger = logging.getLogger(__name__)

class AgentManager:
    def __init__(self):
        self.active_connections: Dict[str, Any] = {} # agent_id -> WebSocket
        self.agent_info: Dict[str, AgentCreate] = {} # agent_id -> AgentCreate
        self.pending_responses: Dict[str, asyncio.Future] = {} # request_id -> Future

    async def register_connection(self, agent_id: str, websocket: Any, agent_data: AgentCreate):
        self.active_connections[agent_id] = websocket
        self.agent_info[agent_id] = agent_data
        logger.info(f"Agent {agent_id} registered and connected.")

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
        if agent_id in self.agent_info:
            self.agent_info[agent_id].status = "offline"
        logger.info(f"Agent {agent_id} disconnected.")

    def get_agent(self, agent_id: str) -> Optional[AgentCreate]:
        return self.agent_info.get(agent_id)

    async def send_command(self, agent_id: str, tool_name: str, arguments: Dict[str, Any], db = None) -> Any:
        """
        Sends a tool execution command to the agent and waits for the response.
        Returns the result or raises an Exception.
        """
        if agent_id not in self.active_connections:
            raise Exception(f"Agent {agent_id} is not connected")

        websocket = self.active_connections[agent_id]
        request_id = str(uuid.uuid4())
        
        # Build JSON-RPC request following AGENT_SSOT.md
        json_rpc_request = {
            "jsonrpc": "2.0",
            "method": "tool.execute",
            "params": {
                "tool_name": tool_name,
                "arguments": arguments,
                "execution_id": request_id
            },
            "id": request_id
        }
        
        # Save to Audit Log
        if db:
            from app.models.db import AuditLog
            audit_entry = AuditLog(
                id=request_id,
                agent_id=agent_id,
                tool_name=tool_name,
                arguments=arguments,
                status="pending"
            )
            db.add(audit_entry)
            db.commit()

        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_responses[request_id] = future
        
        try:
            await websocket.send_text(json.dumps(json_rpc_request))
            logger.info(f"Sent {tool_name} to {agent_id} (req_id: {request_id})")
            
            # Wait for response with timeout (30 seconds)
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Command {request_id} timed out")
            raise Exception("Command execution timed out")
        finally:
            if request_id in self.pending_responses:
                del self.pending_responses[request_id]

    def resolve_response(self, request_id: str, response: Dict[str, Any]):
        """Called by websocket loop when a response arrives."""
        if request_id in self.pending_responses:
            future = self.pending_responses[request_id]
            if "error" in response:
                future.set_exception(Exception(response["error"].get("message", "Unknown error")))
            else:
                future.set_result(response.get("result"))
        else:
            logger.warning(f"Received response for unknown request {request_id}")


