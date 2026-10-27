import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db
from backend.collector.engine import collector_engine
from backend.routers.api_v1 import router as api_v1_router
from backend.routers.ws import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    print("[SRSMon] Initializing SQLite schema...")
    init_db()
    
    # Start Collector Engine
    collector_task = asyncio.create_task(collector_engine.run())
    print("[SRSMon] Collector task launched.")
    
    yield
    
    # Shutdown
    collector_engine.is_running = False
    collector_task.cancel()
    print("[SRSMon] Shutdown completed.")

app = FastAPI(
    title="SAP Replication Server Monitor (SRSMon)",
    description="Operational Health, Partitions & Queues Monitoring Dashboard for DBA Teams",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API and WS routers
app.include_router(api_v1_router)
app.include_router(ws_router)

# Static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "static")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def root():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "SRSMon API running. Please place index.html in frontend/static."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=False)
