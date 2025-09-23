from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from contextlib import asynccontextmanager

from database.connection import get_database, init_database
from routes import portfolio, trades, signals, recommendations, market_data, performance
from services.scheduler_service import TradingSchedulerService
from models.database import Base

# Global scheduler instance
scheduler_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global scheduler_service

    # Startup
    print("🚀 Starting Trading Simulator API...")

    # Initialize database
    await init_database()
    print("✅ Database initialized")

    # Start scheduler service
    scheduler_service = TradingSchedulerService()
    await scheduler_service.start()
    print("✅ Trading scheduler started")

    yield

    # Shutdown
    print("🛑 Shutting down Trading Simulator API...")
    if scheduler_service:
        await scheduler_service.stop()
    print("✅ Shutdown complete")

# Create FastAPI app with lifespan
app = FastAPI(
    title="Trading Simulator API",
    description="A comprehensive stock trading simulation API with real-time data, signals, and recommendations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",  # Alternative port
        "https://*.vercel.app",   # Vercel deployments
        "https://projectin-ten.vercel.app",  # Your specific Vercel domain
        "https://localhost:3000", # HTTPS local
        "*"  # Allow all for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/")
async def root():
    return {
        "message": "Trading Simulator API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check database connection
        db = await get_database()
        if db:
            return {
                "status": "healthy",
                "database": "connected",
                "scheduler": "running" if scheduler_service and scheduler_service.is_running else "stopped"
            }
        else:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "database": "disconnected"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

# Include API routes
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(trades.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["Trading Signals"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(market_data.router, prefix="/api/v1/market", tags=["Market Data"])
app.include_router(performance.router, prefix="/api/v1/performance", tags=["Performance"])

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    print(f"❌ Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# Get scheduler service for dependency injection
def get_scheduler_service():
    return scheduler_service

if __name__ == "__main__":
    # Run with uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development"
    )