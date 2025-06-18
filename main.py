from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.db.database import create_db_and_tables
from app.routers import users, tenants
from app.websocket import endpoints as websocket_endpoints # WebSocket-Router importieren
from app.api.v1.endpoints import sync as sync_endpoints # Sync-API-Router importieren
from app.api.v1.endpoints import websocket_management # WebSocket-Management-API importieren
from app.api.v1.endpoints import user_settings # UserSettings-API importieren
from app.api.v1.endpoints import logos as logo_endpoints # Logo-API importieren
from app.utils.logger import infoLog, errorLog, debugLog # Added debugLog

MODULE_NAME = "MainApp" # Changed to PascalCase for consistency with other module names in logs

@asynccontextmanager
async def lifespan(app: FastAPI):
    infoLog(MODULE_NAME, "Application startup sequence initiated.")
    debugLog(MODULE_NAME, "Lifespan context manager entered.")
    infoLog(MODULE_NAME, "Attempting to create database and tables...")
    try:
        create_db_and_tables()
        infoLog(MODULE_NAME, "Database and tables creation process completed.")
        debugLog(MODULE_NAME, "Successfully called create_db_and_tables.")

        # Backend-Start-Broadcasting nach erfolgreicher Initialisierung
        try:
            # Kurze Verzögerung um sicherzustellen, dass alle Services bereit sind
            await asyncio.sleep(1)
            await websocket_endpoints.broadcast_backend_startup()
            infoLog(MODULE_NAME, "Backend startup broadcast completed.")
        except Exception as broadcast_error:
            # Fehler beim Broadcasting sollten den Start nicht verhindern
            errorLog(
                MODULE_NAME,
                "Error during backend startup broadcast - continuing with startup",
                details={"error": str(broadcast_error), "error_type": type(broadcast_error).__name__}
            )

    except Exception as e:
        errorLog(MODULE_NAME, "Error during database and table creation.", details={"error": str(e), "error_type": type(e).__name__})

    yield

    # Shutdown-Sequenz
    debugLog(MODULE_NAME, "Lifespan context manager exiting.")
    try:
        # Sende Shutdown-Nachricht an alle verbundenen Clients
        await websocket_endpoints.broadcast_backend_status("shutdown")
        infoLog(MODULE_NAME, "Backend shutdown broadcast completed.")
        # Kurze Verzögerung um Clients Zeit zu geben die Nachricht zu verarbeiten
        await asyncio.sleep(0.5)
    except Exception as shutdown_error:
        errorLog(
            MODULE_NAME,
            "Error during backend shutdown broadcast",
            details={"error": str(shutdown_error), "error_type": type(shutdown_error).__name__}
        )

    infoLog(MODULE_NAME, "Application shutting down.")

app = FastAPI(
    title="FinWise Backend API",
    version="0.4.0",
    lifespan=lifespan
)
debugLog(MODULE_NAME, "FastAPI app instance created.", details={"title": app.title, "version": app.version})

origins = [
    "http://localhost:5173", # Vue.js Frontend Development Server
    # Fügen Sie hier weitere Origins hinzu, falls erforderlich (z.B. Produktions-URL)
]
debugLog(MODULE_NAME, "CORS origins defined.", details={"origins": origins})

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
debugLog(MODULE_NAME, "CORS middleware added to the application.")

@app.get("/")
async def root():
    debugLog(MODULE_NAME, "Root endpoint '/' accessed.")
    return {"message": "Welcome to FinWise Backend API"}

@app.get("/ping")
async def ping():
    debugLog(MODULE_NAME, "Ping endpoint '/ping' accessed.")
    return {"status": "online", "message": "FinWise Backend is running"}

app.include_router(users.router)
debugLog(MODULE_NAME, "Users router included.", details={"prefix": users.router.prefix if hasattr(users.router, 'prefix') else 'N/A', "tags": users.router.tags if hasattr(users.router, 'tags') else 'N/A'})
app.include_router(tenants.router)
debugLog(MODULE_NAME, "Tenants router included.", details={"prefix": tenants.router.prefix if hasattr(tenants.router, 'prefix') else 'N/A', "tags": tenants.router.tags if hasattr(tenants.router, 'tags') else 'N/A'})
app.include_router(websocket_endpoints.router, prefix="/ws_finwise") # WebSocket-Router einbinden
debugLog(MODULE_NAME, "WebSocket endpoints router included.", details={"prefix": "/ws_finwise", "tags": websocket_endpoints.router.tags if hasattr(websocket_endpoints.router, 'tags') else 'N/A'})
app.include_router(sync_endpoints.router, prefix="/api/v1/sync", tags=["sync"]) # Sync-API-Router einbinden
debugLog(MODULE_NAME, "Sync API router included.", details={"prefix": "/api/v1/sync", "tags": ["sync"]})
app.include_router(user_settings.router, prefix="/api/v1/user", tags=["user-settings"]) # UserSettings-API-Router einbinden
debugLog(MODULE_NAME, "UserSettings API router included.", details={"prefix": "/api/v1/user", "tags": ["user-settings"]})
app.include_router(websocket_management.router, prefix="/api/v1/websocket", tags=["websocket-management"]) # WebSocket-Management-API einbinden
debugLog(MODULE_NAME, "WebSocket Management API router included.", details={"prefix": "/api/v1/websocket", "tags": ["websocket-management"]})
app.include_router(logo_endpoints.router, prefix="/api/v1/logos", tags=["logos"]) # Logo-API-Router einbinden
debugLog(MODULE_NAME, "Logo API router included.", details={"prefix": "/api/v1/logos", "tags": ["logos"]})

if __name__ == "__main__":
    debugLog(MODULE_NAME, "Application starting with uvicorn (direct execution).", details={"host": "0.0.0.0", "port": 8000})
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
