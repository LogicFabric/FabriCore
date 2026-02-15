# server/app/api/v1/websocket.py
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status, Depends
from typing import Optional
from app.services.agent_manager import AgentManager
from app.services.data_manager import DataManager
from app.core.dependencies import get_agent_manager, get_data_manager, get_db
from app.models.agent import AgentCreate
from sqlalchemy.orm import Session
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, 
    token: Optional[str] = None,
    agent_manager: AgentManager = Depends(get_agent_manager),
    data_manager: DataManager = Depends(get_data_manager), 
    db: Session = Depends(get_db)
):
    await websocket.accept()
    logger.info("New connection request on /api/v1/ws")
    
    agent_id = "unknown"
    
    try:
        # 1. Wait for Identity Handshake
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.error("Received invalid JSON during handshake")
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return
        except Exception as e:
            logger.error(f"Error receiving handshake: {e}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
 
        if message.get("method") != "agent.identify":
            logger.warning(f"Expected agent.identify, got {message.get('method')}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        params = message.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                 logger.error("Failed to decode params string")
                 await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                 return

        agent_id = params.get("agent_id", "unknown")
        
        try:
            memory_total = params.get("os_info", {}).get("memory_total", 0)
            if memory_total is None:
                memory_total = 0
            else:
                memory_total = int(memory_total)
        except (ValueError, TypeError):
             memory_total = 0

        try:
            agent_data = AgentCreate(
                id=agent_id,
                name=params.get("os_info", {}).get("hostname", agent_id),
                status="online",
                platform=params.get("os_info", {}).get("platform", "unknown"),
                hostname=params.get("os_info", {}).get("hostname", "unknown"),
                arch=params.get("os_info", {}).get("arch", "unknown"),
                memory_total=memory_total,
                supported_tools=params.get("capabilities", {}).get("native_tools", [])
            )
        except Exception as e:
            logger.error(f"Agent data validation failed: {e}")
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        # 2. Register Connection in memory and DB
        try:
            await agent_manager.register_connection(agent_id, websocket, agent_data)
            
            data_manager.register_agent({
                "id": agent_id,
                "name": agent_data.name,
                "hostname": agent_data.hostname,
                "platform": agent_data.platform,
                "arch": agent_data.arch,
                "memory_total": agent_data.memory_total,
                "os_info": params.get("os_info", {}),
                "supported_tools": agent_data.supported_tools,
                "status": "online",
                "last_seen": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Failed to register agent in DB/Memory: {e}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        
        # Send Handshake Success
        await websocket.send_text(json.dumps({
            "jsonrpc": "2.0",
            "result": {"status": "registered", "agent_id": agent_id},
            "id": message.get("id")
        }))

        # --- SYNC POLICY ON CONNECT ---
        # Fetch existing policy from DB and push it to the agent immediately
        try:
            policy = data_manager.get_agent_policy(agent_id)
            if policy:
                await agent_manager.sync_policy(agent_id, policy)
        except Exception as e:
            logger.warning(f"Could not sync initial policy for {agent_id}: {e}")

        # 3. Listen Loop
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from {agent_id}: {data}")
            
            try:
                msg = json.loads(data)
                
                # Check if it is a Result to a Command
                if "id" in msg and ("result" in msg or "error" in msg):
                    request_id = msg.get("id")
                    
                    # Notify any waiting futures in AgentManager
                    agent_manager.resolve_response(request_id, msg)
                    
                    from app.models.db import AuditLog
                    audit_entry = db.query(AuditLog).filter(AuditLog.id == request_id).first()
                    if audit_entry:
                        if "error" in msg:
                            audit_entry.status = "error"
                            audit_entry.result = msg.get("error")
                        else:
                            audit_entry.status = "success"
                            audit_entry.result = msg.get("result")
                        
                        audit_entry.completed_at = datetime.utcnow()
                        db.commit()
                        logger.info(f"Updated AuditLog {request_id} with result.")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {agent_id}")
        agent_manager.disconnect(agent_id)
        if agent_id != "unknown":
            data_manager.update_agent_status(agent_id, "offline")
    except Exception as e:
        logger.error(f"Error in websocket endpoint for {agent_id}: {e}")
        agent_manager.disconnect(agent_id)
        if agent_id != "unknown":
            data_manager.update_agent_status(agent_id, "offline")
        try:
            await websocket.close()
        except:
            pass