from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.services.agent_manager import agent_manager
from app.models.agent import Agent

router = APIRouter()

@router.get("/agents", response_model=List[Agent])
async def list_agents():
    # Convert active agents from manager to Agent model list
    # In a real app, we'd fetch from DB and update status based on active connections
    agents = []
    for agent_id, data in agent_manager.agent_info.items():
        agents.append(Agent(
            id=agent_id,
            name=data.name,
            status="online",
            last_seen=datetime.utcnow(), # Placeholder
            platform=data.platform,
            hostname=data.hostname,
            arch=data.arch,
            memory_total=data.memory_total,
            supported_tools=data.supported_tools
        ))
    return agents

@router.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    if agent_id not in agent_manager.agent_info:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = agent_manager.agent_info[agent_id]
    return Agent(
            id=agent_id,
            name=data.name,
            status="online",
            last_seen=datetime.utcnow(),
            platform=data.platform,
            hostname=data.hostname,
            arch=data.arch,
            memory_total=data.memory_total,
            supported_tools=data.supported_tools
    )

@router.post("/agents/{agent_id}/execute")
async def execute_command(agent_id: str, command: Dict[str, Any]):
    """
    Manually trigger a tool execution on an agent.
    Payload example: {"tool_name": "list_files", "arguments": {"path": "."}}
    """
    if agent_id not in agent_manager.agent_info:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # In a real app, we'd validate the command structure here
    await agent_manager.send_command(agent_id, command)
    return {"status": "command_sent", "command": command}

