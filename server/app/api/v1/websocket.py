from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from app.services.agent_manager import agent_manager
from app.models.agent import AgentCreate
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    logger.info(f"New connection request from {agent_id}")
    
    # Create a DB session for this connection lifecycle
    from app.api.deps import SessionLocal
    db = SessionLocal()
    
    try:
        # 1. Wait for Identity Handshake
        data = await websocket.receive_text()
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.error("Received invalid JSON during handshake")
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        if message.get("method") != "agent.identify":
            logger.warning(f"Expected agent.identify, got {message.get('method')}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        params = message.get("params", {})
        
        agent_data = AgentCreate(
            id=agent_id,
            name=params.get("hostname", agent_id),
            status="online",
            platform=params.get("os_info", {}).get("platform", "unknown"),
            hostname=params.get("os_info", {}).get("hostname", "unknown"),
            arch=params.get("os_info", {}).get("arch", "unknown"),
            memory_total=params.get("os_info", {}).get("memory_total", 0),
            supported_tools=params.get("supported_tools", [])
        )

        # 2. Register Connection
        await agent_manager.register_connection(agent_id, websocket, agent_data)
        
        await websocket.send_text(json.dumps({
            "jsonrpc": "2.0",
            "result": {"status": "registered"},
            "id": message.get("id")
        }))

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
                    
                    from app.models.audit_log import AuditLog
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
    except Exception as e:
        logger.error(f"Error in websocket endpoint for {agent_id}: {e}")
        agent_manager.disconnect(agent_id)
        try:
            await websocket.close()
        except:
            pass
    finally:
        db.close()
