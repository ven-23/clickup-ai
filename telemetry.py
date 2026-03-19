import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.langgraph import LanggraphIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
from dotenv import load_dotenv
from sentry_sdk.integrations.mcp import MCPIntegration
from sentry_sdk.integrations.openai import OpenAIIntegration

# Initialize standard logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv()

def init_telemetry():
    """Initializes Sentry with full stack coverage (FastAPI, LangGraph, Logging)."""
    sentry_dsn = os.getenv("SENTRY_DSN")
    
    if not sentry_dsn:
        logger.warning("SENTRY_DSN not found. Sentry monitoring is disabled.")
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        send_default_pii=True,
        traces_sample_rate=1.0,
        integrations=[
            MCPIntegration(include_prompts=True),
            OpenAIIntegration(include_prompts=True),
            FastApiIntegration(),
            LanggraphIntegration(include_prompts=True),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            ),
        ],
    )
    logger.info("Sentry telemetry initialized with coverage: [Performance, MCP, OpenAI, LangGraph, Logging]")

# Initialize immediately on import if DSN is present
if os.getenv("SENTRY_DSN"):
    init_telemetry()

def flush_sentry():
    """Ensures all pending events are sent to Sentry."""
    if os.getenv("SENTRY_DSN"):
        sentry_sdk.flush(timeout=2.0)
