"""
FastAPI Backend for BiteMate
"""
import os
import sys
import datetime
import asyncio
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.bitemate.agents.orchestrator import BiteMateOrchestrator

load_dotenv()

app = FastAPI(
    title="BiteMate API",
    description="AI-powered meal planning assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  ## this is for local prototyping
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = None

def get_orchestrator():
    """Get or create orchestrator instance."""
    global orchestrator
    if orchestrator is None:
        orchestrator = BiteMateOrchestrator()
    return orchestrator


class MealPlanRequest(BaseModel):
    """Request model for meal planning."""
    user_id: str
    user_input: str
    session_id: Optional[str] = None


class MealPlanResponse(BaseModel):
    """Response model for meal planning."""
    user_id: str
    session_id: str
    response: str
    status: str


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "BiteMate API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "meal_plan": "/api/meal-plan (POST)"
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "BiteMate API",
        "orchestrator": "initialized" if orchestrator else "not initialized"
    }


@app.post("/api/meal-plan", response_model=MealPlanResponse)
async def create_meal_plan(request: MealPlanRequest):
    """
    Generate meal plan with dynamic user identification.
    """
    try:
        orch = get_orchestrator()
        
        # Use provided session_id or generate new one
        session_id = request.session_id or f"session_{request.user_id}_{int(datetime.datetime.now().timestamp())}"
        
        # Execute workflow with dynamic user_id
        result = await orch.run_flow(
            user_input=request.user_input,
            user_id=request.user_id,
            session_id=session_id
        )
        
        return MealPlanResponse(
            user_id=request.user_id,
            session_id=session_id,
            response=result if result else "No response generated",
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating meal plan: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.bitemate.api.api:app", host="0.0.0.0", port=8000, reload=True)
