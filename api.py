import telemetry
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from agent import agent_service, clickup_agent
from langchain_core.messages import HumanMessage, AIMessage

import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="ClickUp AI Agent API")
app.mount("/agent", agent_service)

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

class ChatResponse(BaseModel):
    response: str
    sql_queries: Optional[List[str]] = []
    query_results: Optional[List[dict]] = []
    error: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "ClickUp AI Agent API is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info(f"Received chat request: {request.message[:50]}...")
    try:
        # Prepare the state with the new message and history
        messages = []
        for msg in request.history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        
        messages.append(HumanMessage(content=request.message))
        
        # Invoke the agent
        result = clickup_agent.invoke({"messages": messages})
        
        # Extract the final response and metadata
        final_message = result["messages"][-1].content
        sql_queries = result.get("sql_queries", [])
        query_results = result.get("query_results", [])
        error = result.get("error", None)
        
        return ChatResponse(
            response=final_message,
            sql_queries=sql_queries,
            query_results=query_results,
            error=error
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
