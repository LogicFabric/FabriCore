from fastapi import FastAPI
from app.api.v1 import endpoints, websocket
from app.core.config import settings

app = FastAPI(title="FabriCore Server", version="1.0.0")

# Include routers
app.include_router(endpoints.router, prefix="/api/v1", tags=["endpoints"])
app.include_router(websocket.router, prefix="/api/v1", tags=["websocket"])

@app.on_event("startup")
async def startup_event():
    print("FabriCore Server Starting...")
    from app.api.deps import engine
    from app.models.agent import Base as AgentBase
    from app.models.audit_log import Base as AuditBase
    # Create tables
    AgentBase.metadata.create_all(bind=engine)
    AuditBase.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "Welcome to FabriCore"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
