# server/app/services/tools.py
"""
Agent Tools - Defines tools that the LLM can use to control agents.
These tools send JSON-RPC commands to connected agents.
"""

import logging
from typing import Dict, Any, List, Optional
from app.services.data_manager import DataManager

logger = logging.getLogger(__name__)

# Tool definitions that can be passed to the LLM
AGENT_TOOLS = [
    {
        "name": "list_agents",
        "description": "List all connected FabriCore agents and their status.",
        "parameters": {}
    },
    {
        "name": "run_command",
        "description": "Execute a shell command on a specific agent. Use with caution.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The ID of the agent to run the command on"},
            "command": {"type": "string", "description": "The shell command to execute"}
        }
    },
    {
        "name": "get_system_info",
        "description": "Get system information (CPU, memory, disk) from an agent.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The ID of the agent"}
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory on an agent.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The ID of the agent"},
            "path": {"type": "string", "description": "The directory path to list"}
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file on an agent.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The ID of the agent"},
            "path": {"type": "string", "description": "The file path to read"}
        }
    },
    {
        "name": "get_agent_details",
        "description": "Get detailed information about a specific agent.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The ID of the agent"}
        }
    }
]


class ToolExecutor:
    """Executes tools by dispatching commands to agents."""
    
    def __init__(self, data_manager: DataManager, comm_manager):
        self.db = data_manager
        self.comm = comm_manager
        self.pending_requests: Dict[str, Any] = {}
    
    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        logger.info(f"Executing tool: {tool_name} with params: {params}")
        
        try:
            if tool_name == "list_agents":
                return await self._list_agents()
            elif tool_name == "run_command":
                return await self._run_command(params["agent_id"], params["command"])
            elif tool_name == "get_system_info":
                return await self._get_system_info(params["agent_id"])
            elif tool_name == "list_files":
                return await self._list_files(params["agent_id"], params["path"])
            elif tool_name == "read_file":
                return await self._read_file(params["agent_id"], params["path"])
            elif tool_name == "get_agent_details":
                return await self._get_agent_details(params["agent_id"])
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {"error": str(e)}
    
    async def _list_agents(self) -> Dict[str, Any]:
        """List all connected agents from the database."""
        db = self.db.get_db()
        try:
            from app.models.db import Agent
            agents = db.query(Agent).all()
            agent_list = [{
                "id": a.id,
                "hostname": a.hostname,
                "status": a.status,
                "platform": a.platform,
                "last_seen": a.last_seen.isoformat() if a.last_seen else None
            } for a in agents]
            return {
                "success": True,
                "agents": agent_list,
                "count": len(agent_list)
            }
        finally:
            db.close()
    
    async def _run_command(self, agent_id: str, command: str) -> Dict[str, Any]:
        """Send a command execution request to an agent."""
        import uuid
        request_id = str(uuid.uuid4())
        
        # Build JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "method": "sys.exec",
            "params": {
                "command": command,
                "timeout": 30
            },
            "id": request_id
        }
        
        # Check if agent is connected
        if agent_id not in self.comm.active_connections:
            return {"error": f"Agent {agent_id} is not connected"}
        
        # Send the request
        await self.comm.send_message(agent_id, request)
        
        # TODO: Implement proper response waiting with asyncio.Future
        # For now, return acknowledgment
        return {
            "success": True,
            "message": f"Command sent to agent {agent_id}",
            "request_id": request_id,
            "note": "Response handling not yet implemented - check agent logs"
        }
    
    async def _get_system_info(self, agent_id: str) -> Dict[str, Any]:
        """Request system info from an agent."""
        import uuid
        request_id = str(uuid.uuid4())
        
        request = {
            "jsonrpc": "2.0",
            "method": "sys.resources",
            "params": {},
            "id": request_id
        }
        
        if agent_id not in self.comm.active_connections:
            return {"error": f"Agent {agent_id} is not connected"}
        
        await self.comm.send_message(agent_id, request)
        return {
            "success": True,
            "message": f"System info request sent to agent {agent_id}",
            "request_id": request_id
        }
    
    async def _list_files(self, agent_id: str, path: str) -> Dict[str, Any]:
        """Request file listing from an agent."""
        import uuid
        request_id = str(uuid.uuid4())
        
        request = {
            "jsonrpc": "2.0",
            "method": "sys.listdir",
            "params": {"path": path},
            "id": request_id
        }
        
        if agent_id not in self.comm.active_connections:
            return {"error": f"Agent {agent_id} is not connected"}
        
        await self.comm.send_message(agent_id, request)
        return {
            "success": True,
            "message": f"File list request sent to agent {agent_id} for path: {path}",
            "request_id": request_id
        }
    
    async def _read_file(self, agent_id: str, path: str) -> Dict[str, Any]:
        """Request file content from an agent."""
        import uuid
        request_id = str(uuid.uuid4())
        
        request = {
            "jsonrpc": "2.0",
            "method": "sys.readfile",
            "params": {"path": path},
            "id": request_id
        }
        
        if agent_id not in self.comm.active_connections:
            return {"error": f"Agent {agent_id} is not connected"}
        
        await self.comm.send_message(agent_id, request)
        return {
            "success": True,
            "message": f"File read request sent to agent {agent_id} for: {path}",
            "request_id": request_id
        }
    
    async def _get_agent_details(self, agent_id: str) -> Dict[str, Any]:
        """Get agent details from database."""
        db = self.db.get_db()
        try:
            from app.models.db import Agent
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"error": f"Agent {agent_id} not found"}
            
            return {
                "success": True,
                "agent": {
                    "id": agent.id,
                    "hostname": agent.hostname,
                    "status": agent.status,
                    "platform": agent.platform,
                    "os_info": agent.os_info,
                    "capabilities": agent.capabilities,
                    "last_seen": agent.last_seen.isoformat() if agent.last_seen else None
                }
            }
        finally:
            db.close()


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get tool definitions for the LLM."""
    return AGENT_TOOLS
