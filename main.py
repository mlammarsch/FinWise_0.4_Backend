from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.database import create_db_and_tables
from app.routers import users, tenants
from app.utils.logger import infoLog, errorLog

MODULE_NAME = "main"

@asynccontextmanager
async def lifespan(app: FastAPI):
    infoLog(MODULE_NAME, "Application startup sequence initiated.")
    infoLog(MODULE_NAME, "Attempting to create database and tables...")
    try:
        create_db_and_tables()
        infoLog(MODULE_NAME, "Database and tables creation process completed.")
    except Exception as e:
        errorLog(MODULE_NAME, "Error during database and table creation.", {"error": str(e)})
    yield
    infoLog(MODULE_NAME, "Application shutting down.")

app = FastAPI(
    title="FinWise Backend API",
    version="0.4.0",
    lifespan=lifespan
)

origins = [
    "http://localhost:5173", # Vue.js Frontend Development Server
    # Fügen Sie hier weitere Origins hinzu, falls erforderlich (z.B. Produktions-URL)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to FinWise Backend API"}

app.include_router(users.router)
app.include_router(tenants.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
