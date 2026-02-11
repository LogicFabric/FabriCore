# server/app/main.py
from fastapi import FastAPI
from app.api.routers import router
from nicegui import ui # NiceGUI
import uvicorn

app = FastAPI(title="FabriCore Server")

# Include API Router
app.include_router(router)

# Mount NiceGUI (Using ui.run_with which handles the lifecycle with FastAPI)
from app.ui.main import init_ui
init_ui()
ui.run_with(app, storage_secret='secret_key')

@app.get("/")
def read_root():
    return {"message": "FabriCore Server Running"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
