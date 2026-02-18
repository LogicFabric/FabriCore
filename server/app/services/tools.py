# server/app/services/tools.py
"""
Agent Tools - Defines tools that the LLM can use to control agents.
These tools send JSON-RPC commands to connected agents.
"""

import logging
import json
import uuid
from typing import Dict, Any, List, Optional
from app.services.data_manager import DataManager
from app.core.dependencies import get_agent_manager

logger = logging.getLogger(__name__)

# Tool definitions that can be passed to the LLM
AGENT_TOOLS = [
    {
        "name": "list_agents",
        "description": "Returns a list of all connected agents. Use this to find available agent_ids.",
        "parameters": {}
    },
    {
        "name": "run_command",
        "description": "Executes a shell command. REQUIRED: 'agent_id' and 'command'.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The exact ID of the agent (e.g., agent-dev-toke)"},
            "command": {"type": "string", "description": "The shell command to run (e.g., 'ls -la', 'df -h')"}
        }
    },
    {
        "name": "get_system_info",
        "description": "Get system information (CPU, memory, disk). REQUIRED: 'agent_id'.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The exact ID of the agent"}
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory. REQUIRED: 'agent_id' and 'path'.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The exact ID of the agent"},
            "path": {"type": "string", "description": "The directory path to list (e.g., '/var/log')"}
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file. REQUIRED: 'agent_id' and 'path'.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The exact ID of the agent"},
            "path": {"type": "string", "description": "The file path to read"}
        }
    },
    {
        "name": "get_agent_details",
        "description": "Get detailed metadata about a specific agent. REQUIRED: 'agent_id'.",
        "parameters": {
            "agent_id": {"type": "string", "description": "The exact ID of the agent"}
        }
    }
]


class ToolExecutor:
    """Executes tools by dispatching commands to agents."""
    
    def __init__(self, data_manager: DataManager, comm_manager=None):
        self.db = data_manager
        self.agent_manager = get_agent_manager() # Use Dependency Injection
        self.pending_requests: Dict[str, Any] = {}
    
    async def execute(self, tool_name: str, params: Dict[str, Any], approved_by: Optional[str] = None) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        logger.info(f"Executing tool: {tool_name} with params: {params} (approved_by={approved_by})")
        
        # 1. Validate Tool Existence
        valid_tools = [t['name'] for t in AGENT_TOOLS]
        if tool_name not in valid_tools:
            return {
                "status": "error", 
                "message": f"Tool '{tool_name}' does not exist. Available tools: {', '.join(valid_tools)}. Please verify the tool name and try again."
            }

        # 2. Server-side HITL Policy Check
        agent_id = params.get("agent_id")
        if agent_id and not approved_by and tool_name != "list_agents":
            try:
                policy = self.db.get_agent_policy(agent_id)
                if policy.get('hitl_enabled', False):
                    requires_approval = [x.strip().lower() for x in policy.get('requires_approval_for', []) if x.strip()]
                    blocked_commands = [x.strip().lower() for x in policy.get('blocked_commands', []) if x.strip()]

                    # Map tool names to underlying shell commands for matching
                    TOOL_TO_COMMANDS = {
                        "list_files": ["ls"],
                        "read_file": ["cat"],
                        "run_command": [],  # dynamic — checked via params
                        "get_system_info": ["uname", "sysinfo"],
                        "get_agent_details": [],
                    }

                    # Resolve the actual shell command(s) this tool will execute
                    tool_commands = TOOL_TO_COMMANDS.get(tool_name, [])
                    if tool_name == "run_command" and "command" in params:
                        # Extract the base command from the full command string
                        shell_cmd = params["command"].strip().split()[0].lower() if params["command"].strip() else ""
                        tool_commands = [shell_cmd] if shell_cmd else []

                    # Check requires_approval: match on tool name OR underlying command
                    if tool_name.lower() in requires_approval:
                        logger.info(f"HITL: Tool '{tool_name}' requires approval for agent {agent_id}")
                        return {
                            "status": "paused",
                            "message": f"Tool '{tool_name}' requires human approval for agent {agent_id}."
                        }
                    for cmd in tool_commands:
                        if cmd in requires_approval:
                            logger.info(f"HITL: Command '{cmd}' (via tool '{tool_name}') requires approval for agent {agent_id}")
                            return {
                                "status": "paused",
                                "message": f"Command '{cmd}' requires human approval for agent {agent_id}."
                            }

                    # Check blocked_commands: match on tool name OR underlying command
                    if tool_name.lower() in blocked_commands:
                        return {
                            "status": "error",
                            "message": f"Tool '{tool_name}' is blocked by security policy for agent {agent_id}."
                        }
                    for cmd in tool_commands:
                        if cmd in blocked_commands:
                            return {
                                "status": "error",
                                "message": f"Command '{cmd}' is blocked by security policy for agent {agent_id}."
                            }

            except Exception as e:
                logger.warning(f"HITL policy check failed: {e}")

        try:
            if tool_name == "list_agents":
                return await self._list_agents()
            elif tool_name == "run_command":
                if "agent_id" not in params or "command" not in params:
                    return {"status": "error", "message": "Missing required parameters: 'agent_id' and 'command'"}
                return await self._run_command(params["agent_id"], params["command"], approved_by)
            elif tool_name == "get_system_info":
                if "agent_id" not in params:
                    return {"status": "error", "message": "Missing required parameter: 'agent_id'"}
                return await self._get_system_info(params["agent_id"])
            elif tool_name == "list_files":
                if "agent_id" not in params or "path" not in params:
                    return {"status": "error", "message": "Missing required parameters: 'agent_id' and 'path'"}
                return await self._list_files(params["agent_id"], params["path"], approved_by)
            elif tool_name == "read_file":
                if "agent_id" not in params or "path" not in params:
                    return {"status": "error", "message": "Missing required parameters: 'agent_id' and 'path'"}
                return await self._read_file(params["agent_id"], params["path"], approved_by)
            elif tool_name == "get_agent_details":
                if "agent_id" not in params:
                    return {"status": "error", "message": "Missing required parameter: 'agent_id'"}
                return await self._get_agent_details(params["agent_id"])
            else:
                return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            error_msg = str(e)
            
            # Check for HITL specific error code from Agent (-32001)
            if "Action requires approval" in error_msg or "-32001" in error_msg:
                # HITL Flow
                import re
                match = re.search(r'execution_id":\s*"([^"]+)"', error_msg)
                execution_id = match.group(1) if match else f"need-approval-{uuid.uuid4()}"
                
                from app.core.dependencies import get_db
                from app.models.db import PendingApproval
                
                try:
                    db = next(get_db())
                    # Check if already exists to prevent duplicates
                    exists = db.query(PendingApproval).filter(PendingApproval.execution_id == execution_id).first()
                    if not exists:
                        approval = PendingApproval(
                            id=str(uuid.uuid4()),
                            execution_id=execution_id,
                            agent_id=params.get("agent_id", "unknown"),
                            tool_name=tool_name,
                            arguments=params,
                            status="pending"
                        )
                        db.add(approval)
                        db.commit()
                        db.close()
                except Exception as db_e:
                    logger.error(f"Failed to save pending approval: {db_e}")
                
                return {
                    "status": "paused", 
                    "message": "Action requires approval. Admin notified. Please wait for approval."
                }

            return {"status": "error", "message": f"Execution failed: {str(e)}"}
    
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
    
    async def _run_command(self, agent_id: str, command: str, approved_by: Optional[str] = None) -> Dict[str, Any]:
        """Execute a shell command on an agent and return the real result."""
        db = self.db.get_db()
        try:
            parts = command.split()
            cmd_name = parts[0]
            cmd_args = parts[1:] if len(parts) > 1 else []
            
            result = await self.agent_manager.send_command(
                agent_id=agent_id,
                tool_name="exec_command",
                arguments={
                    "command": cmd_name,
                    "args": cmd_args,
                    "timeout": 30
                },
                db=db,
                approved_by=approved_by  # Pass approval
            )
            return {"success": True, "output": result.get("output", ""), "agent_id": agent_id}
        finally:
            db.close()
    
    async def _get_system_info(self, agent_id: str) -> Dict[str, Any]:
        db = self.db.get_db()
        try:
            result = await self.agent_manager.send_command(
                agent_id=agent_id,
                tool_name="get_system_info",
                arguments={},
                db=db
            )
            return {"success": True, "info": result, "agent_id": agent_id}
        finally:
            db.close()
    
    async def _list_files(self, agent_id: str, path: str, approved_by: Optional[str] = None) -> Dict[str, Any]:
        db = self.db.get_db()
        try:
            result = await self.agent_manager.send_command(
                agent_id=agent_id,
                tool_name="exec_command",
                arguments={
                    "command": "ls",
                    "args": ["-la", path],
                    "timeout": 10
                },
                db=db,
                approved_by=approved_by
            )
            return {"success": True, "output": result.get("output", ""), "path": path}
        finally:
            db.close()
    
    async def _read_file(self, agent_id: str, path: str, approved_by: Optional[str] = None) -> Dict[str, Any]:
        db = self.db.get_db()
        try:
            result = await self.agent_manager.send_command(
                agent_id=agent_id,
                tool_name="exec_command",
                arguments={
                    "command": "cat",
                    "args": [path],
                    "timeout": 10
                },
                db=db,
                approved_by=approved_by
            )
            return {"success": True, "content": result.get("output", ""), "path": path}
        finally:
            db.close()
    
    async def _get_agent_details(self, agent_id: str) -> Dict[str, Any]:
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