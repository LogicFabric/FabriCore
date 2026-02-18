from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.services.agent_manager import AgentManager
from app.core.dependencies import get_agent_manager
from app.models.agent import Agent

router = APIRouter()

@router.get("/agents", response_model=List[Agent])
async def list_agents(agent_manager: AgentManager = Depends(get_agent_manager)):
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
async def get_agent(agent_id: str, agent_manager: AgentManager = Depends(get_agent_manager)):
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
async def execute_command(agent_id: str, command: Dict[str, Any], agent_manager: AgentManager = Depends(get_agent_manager)):
    """
    Manually trigger a tool execution on an agent.
    Payload example: {"tool_name": "list_files", "arguments": {"path": "."}}
    """
    if agent_id not in agent_manager.agent_info:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # In a real app, we'd validate the command structure here
    await agent_manager.send_command(agent_id, command)
    return {"status": "command_sent", "command": command}

@router.post("/webpush/subscribe")
async def subscribe_to_push(sub_data: Dict[str, Any]):
    """
    Save a web push subscription to the database.
    """
    from app.services.data_manager import DataManager
    from app.models.db import PushSubscription
    
    data_manager = DataManager()
    db = data_manager.SessionLocal()
    try:
        # Extract endpoint and keys
        endpoint = sub_data.get("endpoint")
        keys = sub_data.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        
        if not endpoint or not p256dh or not auth:
            raise HTTPException(status_code=400, detail="Invalid subscription data")
            
        # Create or update subscription
        existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
        if existing:
            existing.p256dh = p256dh
            existing.auth = auth
        else:
            new_sub = PushSubscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=None # Optional: could be passed from frontend
            )
            db.add(new_sub)
        
        db.commit()
        return {"status": "subscribed"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
