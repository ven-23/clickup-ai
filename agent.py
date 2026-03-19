import os
import time
from typing import Annotated, TypedDict, List
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from fastapi import FastAPI
import telemetry
import logging

logger = logging.getLogger(__name__)

agent_service = FastAPI()

@agent_service.get("/sentry-debug")
async def trigger_error():
    logger.info("Triggering Sentry debug error...")
    division_by_zero = 1 / 0

# Import the fast MCP components
import mcp_server

# Load environment variables
load_dotenv()

# LangChain Tracing (Removed to minimize costs)

import operator
from typing import Annotated, TypedDict, List, Union

# Define the state of our agent
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    query_results: List[dict]
    error: str
    attempts: int

# Initialize the LLM - Single Model (GPT-4o-mini) for all tasks
model = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=300)

# Bind MCP Tools to the Model
tools = [
    mcp_server.execute_query,
    mcp_server.get_column_info,
    mcp_server.get_dataset_stats
]
model_with_tools = model.bind_tools(tools)

# 1. Query Generation Node
def generate_sql(state: AgentState):
    """Analyzes the user request and generates optimized SQL queries."""
    # ... (rest of the code remains the same but uses heavy_model)
    user_query = ""
    for m in reversed(state['messages']):
        if isinstance(m, HumanMessage):
            user_query = m.content
            break
            
    if "test error" in user_query.lower():
        logger.error(f"User triggered intentional test error: {user_query}")
        raise ValueError(f"Intentional Sentry Test Error: {user_query}")
    
    dataset_context = """
    DATASET METADATA:
    - Files Analyzed: 'Mar-Jul2025.csv' and 'Sep-Jan.csv' are the two primary datasets.
    - Time Period: August 1, 2024, to July 31, 2025 (Gap in Feb 2025).
    - Scope: ClickUp time tracking for Shore360Agency, AussieBum, etc.
    
    DATASET GROUND TRUTHS:
    - Status 'completed' (22,783) vs List 'Completed' (480).
    - Status 'in progress' (10,578) vs List 'WIP' (9,477).
    - Space 'Private' (94 entries) vs 'Delivery' (63,156 entries).
    - No Tags count: 11,229 (Query: `WHERE tags = '[]'`).
    - Sunday (2,562), Monday (13,318) - USE start_time in UTC.
    - High-Value Users (>1,500 hrs): There are **39** users meeting this global threshold in the dataset.
    - Zero Time Tasks: There are 20 tasks with 0 tracked time (6 'completed' status).
    - Urgency: 'ZZZ TEST CLIENT' has 1 'Critical' task. 'WBP Group' and '6 Degrees Media' are tied for highest average at **3.0** (High).
    """

    system_prompt = """
    You are an expert SQL analyst for a dataset of ClickUp time entries for Shore360Agency, AussieBum, and others.
    
    CAPABILITIES:
    1. `get_column_info`: Call this if you need to see the table schema or column details.
    2. `get_dataset_stats`: Call this for high-level numbers (total rows, date range).
    3. `execute_query`: Use this to run SQL and get data.
    
    CRITICAL RULES:
    1. MANDATORY "DONE" MAPPING: User says "done"/"completed" -> Use `WHERE task_status IN ('done', 'completed')`.
    2. KEYWORD SEARCH: Use singular stems (e.g., `%chore%`) across `task_name`, `description`, `space_name`, `folder_name`, and `list_name`.
    3. TEMPORAL CONTEXT: Aug-Dec use 2024. Jan-Jul use 2025.
    4. NO HALLUCINATION: If unsure about columns, CALL `get_column_info` FIRST.
    5. ONLY SQL: Use `execute_query` for data. Do not assume data exists without querying.
    """

    # If this is the first message and it's a data query, we can help the model by 
    # letting it know it should probably check the schema if it's not a generic question.
    messages = [{"role": "system", "content": system_prompt}] + state['messages']
    
    if state.get('error'):
        messages.append({"role": "user", "content": f"Previous attempt failed: {state['error']}. Please fix and try again."})

    response = model_with_tools.invoke(messages)
    return {"messages": [response], "attempts": state.get('attempts', 0) + 1}

# 2. Tool Execution Node
def execute_sql(state: AgentState):
    """Executes tool calls through the MCP dispatcher to ensure Sentry visibility."""
    import asyncio
    last_message = state['messages'][-1]
    
    if not last_message.tool_calls:
        return {"error": "No tools were called."}
    
    tool_messages = []
    query_results = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        try:
            # CALL THROUGH MCP DISPATCHER (for Sentry Instrumentation)
            # This triggers the MCP SDK lifecycle that Sentry hooks into
            
            # FastMCP tools are async coroutines that must be awaited
            result_data = asyncio.run(mcp_server.mcp.call_tool(tool_name, tool_args))
            
            if tool_name == "execute_query":
                query_results.extend(result_data)
                content = mcp_server.results_to_markdown(result_data)
            elif tool_name == "get_column_info":
                content = result_data
            elif tool_name == "get_dataset_stats":
                content = str(result_data)
            else:
                content = str(result_data)
                
            tool_messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=str(content)
            ))
        except Exception as e:
            logger.error(f"MCP Tool Execution Error ({tool_name}): {e}")
            tool_messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=f"Error executing tool: {str(e)}"
            ))

    return {
        "messages": tool_messages, 
        "query_results": query_results,
        "error": None
    }

# 3. Final Formatting Node (Beautifier)
def format_response(state: AgentState):
    """Uses the LLM to beautify the raw data into a premium response if needed."""
    if state.get('error') or not state.get('query_results'):
        return {}
    
    last_user_query = ""
    for m in reversed(state['messages']):
        if isinstance(m, HumanMessage):
            last_user_query = m.content
            break
            
    beautify_keywords = ["high-value", "ratio", "discrepancy", "are there", "is there", "any tasks"]
    if any(k in last_user_query.lower() for k in beautify_keywords):
        prompt = f"""
        Beautify the following data into a premium, professional response.
        User Question: {last_user_query}
        Raw Data (From SQL): {state['query_results']}
        
        RULES:
        1. If the question is "Are there any..." or "Is there...", the VERY FIRST word of your response MUST be "Yes" or "No".
        2. USE THE ACTUAL NAMES AND NUMBERS FROM THE RAW DATA. DO NOT USE PLACEHOLDERS.
        3. For "High-Value Users", use this EXACT style:
           High-Value Users ( > 1,500 hours tracked ):
           1. [Name] — [Hours] hours
           ...
           **Total High-Value Users: [Count] users.**
        4. If there are too many items, list only the top 10.
        5. Return ONLY the beautified text.
        """
        response = model.invoke([{"role": "user", "content": prompt}])
        return {"messages": [AIMessage(content=response.content.strip())]}
    
    return {}

# Build the Graph - Modularized & Fast
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("generator", generate_sql)
workflow.add_node("executor", execute_sql)
workflow.add_node("formatter", format_response)

# Conditional Router for Self-Correction
def should_continue(state: AgentState):
    """Determines whether to continue tool execution or move to formatting."""
    last_message = state['messages'][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "executor"
    return "formatter"

workflow.set_entry_point("generator")
workflow.add_conditional_edges("generator", should_continue, {
    "executor": "executor",
    "formatter": "formatter"
})
workflow.add_edge("executor", "generator")
workflow.add_edge("formatter", END)

clickup_agent = workflow.compile()

# Interactive loop
if __name__ == "__main__":
    print("ClickUp AI Agent Ready (V8 Modular MCP). Type 'exit' to quit.")
    while True:
        user_input = input("\nYour Question: ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        inputs = {"messages": [HumanMessage(content=user_input)]}
        start_time = time.time()
        try:
            final_state = clickup_agent.invoke(inputs)
            end_time = time.time()
            duration = end_time - start_time
            
            if final_state.get('messages') and isinstance(final_state['messages'][-1], AIMessage):
                print(f"\nAI Result:\n{final_state['messages'][-1].content}")
                print(f"\n(Response time: {duration:.2f} seconds)")
            elif final_state.get('error'):
                print(f"\nAI ERROR: {final_state['error']}")
            else:
                print("\nAI Result: I'm sorry, I couldn't process that request.")
        except Exception as e:
            logger.error(f"Error during agent invocation: {e}")
            telemetry.flush_sentry()
            print(f"\nAn error occurred: {e}")
            print("The error has been logged to Sentry.")
