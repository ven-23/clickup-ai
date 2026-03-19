import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List
from datetime import datetime
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Sentry Monitoring Setup
import sentry_sdk
try:
    from sentry_sdk.integrations.mcp import MCPIntegration
except ImportError:
    MCPIntegration = None

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    integrations = []
    if MCPIntegration:
        integrations.append(MCPIntegration(include_prompts=True))

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=integrations,
        send_default_pii=True,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# Initialize FastMCP Server
mcp = FastMCP("ClickUp Analyst")

# Database configuration
DB_URL = os.getenv("DB_URL", "postgresql://clickup_user:clickup_pass@localhost:5433/clickup_db")

# MCP Schema Definition (The 60+ Column Data Dictionary)
MCP_SCHEMA = """
You are an expert SQL assistant for a single table: time_entries.
Table: time_entries

COLUMNS:
- id (SERIAL PRIMARY KEY) - Internal ID.
- time_entry_id (TEXT) - The unique ClickUp task ID (e.g., '8696g0v43').
- username (TEXT) - Person tracking time (names cleaned of brackets). For specific name queries, use exact matches or `ILIKE` for the full name only.
- task_name, task_status, description (TEXT)
- space_name, folder_name, list_name (TEXT)
- start_time, stop_time, date_created (TIMESTAMPTZ)
- time_tracked_ms (BIGINT) - Time in milliseconds.
- client_project_name (TEXT) - Primary client.
- agency_name (TEXT) - Agency associated.
- project_manager, requestor (TEXT) - Cleaned names.
- parent_task_id (TEXT) - Relationship ID.
- tags (JSONB) - A JSON array of tags.
- checklists (TEXT)
- job_number, po_number, invoice_no (TEXT)
- job_type, project_identifier (TEXT)
- urgency (TEXT)
- on_track (BOOLEAN)
- days_left (NUMERIC)
- billable, billed (BOOLEAN)
- hours_to_bill (NUMERIC)
- billing_method, invoice_method, billing_instructions (TEXT)
- task_time_estimated, task_time_spent (BIGINT)
- prepaid_hours (NUMERIC)

ACCURACY & PERFORMANCE RULES:
1. MONTH INTELLIGENCE (MANDATORY):
   - JANUARY: 1, FEBRUARY: 2, MARCH: 3, APRIL: 4, MAY: 5, JUNE: 6, JULY: 7, AUGUST: 8, SEPTEMBER: 9, OCTOBER: 10, NOVEMBER: 11, DECEMBER: 12.
   - To filter by month, use `EXTRACT(MONTH FROM stop_time)`.
2. TEMPORAL CONTEXT (CRITICAL):
   - The dataset spans **August 2024** to **July 2025**.
   - For JAN, FEB, MAR, APR, MAY, JUN, JUL: Use **YEAR 2025**.
   - For AUG, SEP, OCT, NOV, DEC: Use **YEAR 2024**.
   - Example for September: `WHERE EXTRACT(MONTH FROM stop_time) = 9 AND EXTRACT(YEAR FROM stop_time) = 2024`.
   - If the user asks for "Total tracked time for July", they likely mean the 2025 instance.
3. NAMES: Use `username = 'Full Name'` for 100% precision.
4. AGGREGATION: Always use `GROUP BY` and `SUM(time_tracked_ms)` for totals/summaries.
5. SQL RECIPES:
   - BILLABLE RATIO: `ROUND(SUM(billable_hours::int) / NULLIF(SUM(time_tracked_ms/3600000.0), 0), 2)`.
   - LONGEST: `ORDER BY LENGTH(description) DESC NULLS LAST LIMIT 1`.
6. FULL ANSWER POLICY: Always include `task_name`, `username`, and `client_project_name` **ONLY for detail/list queries**. 
   - NEVER include these columns in aggregation/summary queries (e.g., `SUM`, `COUNT`) as it breaks the grouping and returns too many rows.
7. TIME FORMATTING: Express time in hours: `(SUM(time_tracked_ms)/3600000.0)`.
8. NULL SAFETY: Use `NULLS LAST` when sorting.
9. TAG ANALYSIS (CRITICAL):
   - To count or analyze individual tags, you MUST unnest them using `CROSS JOIN jsonb_array_elements_text(tags)`.
   - Example (Most used tag): `SELECT tag, COUNT(*) as frequency_count FROM time_entries, jsonb_array_elements_text(tags) as tag GROUP BY tag ORDER BY frequency_count DESC LIMIT 1`.
   - Example (Filter by tag): `SELECT * FROM time_entries WHERE tags @> '["smoko"]'::jsonb`.
   - AVG COMPLETION TIME: `SELECT project_manager, AVG(time_tracked_ms)/3600000.0 as avg_hrs FROM time_entries WHERE task_status = 'completed' GROUP BY project_manager ORDER BY avg_hrs DESC`.
10. NO HALLUCINATION: Run SQL for all data keywords.
11. META-QUERIES (CRITICAL): If the user asks "about the database", "what database", or "how many rows", you MUST return SQL like `SELECT COUNT(*) as total_rows, MIN(stop_time) as earliest_date, MAX(stop_time) as latest_date FROM time_entries`. Do NOT refuse to provide details.
12. NO PERMISSION: Provide data immediately.

Return ONLY the SQL query OR the CONVERSATION message.
"""

@mcp.tool()
def results_to_markdown(results: List[dict]) -> str:
    """Instantly converts query results into the most appropriate terminal format with width awareness."""
    import os
    try:
        term_width = os.get_terminal_size().columns
    except OSError:
        term_width = 120
    
    if not results:
        return "No results found. Try adjusting your search or filters."
    
    headers = list(results[0].keys())
    row_count = len(results)
    
    def densify(val, h):
        if val is None: return "-"
        h_lower = h.lower()

        # Month Translation Logic: Convert numeric month (1-12) to Name
        if "month" in h_lower and (isinstance(val, (int, float, complex)) or hasattr(val, '__float__') and not isinstance(val, bool)):
            try:
                m_idx = int(float(val))
                months = ["None", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                if 1 <= m_idx <= 12: return months[m_idx]
            except: pass

        # DOW Translation Logic: Convert numeric DOW (0-6) to Name
        if "dow" in h_lower and (isinstance(val, (int, float, complex)) or hasattr(val, '__float__') and not isinstance(val, bool)):
            try:
                d_idx = int(float(val))
                days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                if 0 <= d_idx <= 6: return days[d_idx]
            except: pass

        # Advanced Time Heuristic: Catch any time-related column and format as hours
        is_time_col = any(k in h_lower for k in ['time', 'tracked', 'duration', 'spent', 'estimated', 'hrs']) and 'count' not in h_lower
        
        if (isinstance(val, (int, float, complex)) or (hasattr(val, '__float__') and not isinstance(val, bool))) and is_time_col:
            try:
                f_val = float(val)
                # If it's a large integer or explicitly marked as ms, divide.
                # If it's already a float/decimal, assume the agent already converted to hours (Rule 7).
                if "ms" in h_lower or (isinstance(val, int) and f_val > 5000):
                    return f"{f_val / 3600000.0:.2f} hrs"
                return f"{f_val:.2f} hrs"
            except: pass

        # Round any non-time float/decimal value to 2 places
        if isinstance(val, (float, complex)):
            return f"{val:.2f}"
        if hasattr(val, '__float__') and not isinstance(val, (int, bool)):
            return f"{float(val):.2f}"
            
        # Human-Friendly Dates: Handle datetime objects from psycopg2
        if isinstance(val, datetime):
            if val.day == 1 and val.hour == 0 and val.minute == 0:
                return val.strftime('%B %Y')
            return val.strftime('%Y-%m-%d %H:%M')

        v_str = str(val)
        if "-" in v_str[0:5] and ":" in v_str and len(v_str) > 16:
            v_str = v_str[:16]
        return v_str

    # 1. SINGLE VALUE CASE
    if row_count == 1 and len(headers) == 1:
        val = densify(results[0][headers[0]], headers[0])
        label = headers[0].replace('_', ' ').title()
        return f"{label}: {val}"
    
    # helper: Vertical List Formatter
    def build_list_view(data):
        output = []
        for i, row in enumerate(data):
            output.append(f"--- RESULT {i+1} ---")
            for h in headers:
                val = densify(row[h], h)
                output.append(f"{h.replace('_', ' ').upper().ljust(20)}: {val}")
            output.append("")
        return "\n".join(output)

    # 2. SINGLE RECORD CASE
    if row_count == 1:
        return build_list_view(results)
    
    # 3. MULTIPLE RECORDS CASE: Calculate widths
    col_widths = {h: len(h.replace('_', ' ')) for h in headers}
    for row in results:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(densify(row[h], h)))
    
    # AUTO-SWITCH: If table is still wider than terminal after densification, use List View
    total_width = sum(col_widths.values()) + (len(headers) * 3)
    if total_width > term_width:
        # If it's too wide, a vertical list is much better than a wrapped table
        return build_list_view(results)

    # Build ASCII Table
    h_row = " | ".join(h.replace('_', ' ').upper().ljust(col_widths[h]) for h in headers)
    s_row = "-+-".join("-" * col_widths[h] for h in headers)
    rows = []
    for row in results:
        rows.append(" | ".join(densify(row[h], h).ljust(col_widths[h]) for h in headers))
    
    return "\n".join([h_row, s_row] + rows)

@mcp.tool()
def execute_query(query: str) -> List[dict]:
    """Connects to the database and executes the provided SQL query."""
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            results = cur.fetchmany(100)
        return results
    finally:
        conn.close()

@mcp.tool()
def get_column_info() -> str:
    """Returns the data dictionary/schema for the time_entries table."""
    return MCP_SCHEMA

@mcp.tool()
def get_dataset_stats() -> dict:
    """Returns high-level statistics about the dataset (count, range, etc)."""
    query = "SELECT COUNT(*) as total_rows, MIN(stop_time) as earliest_date, MAX(stop_time) as latest_date FROM time_entries"
    results = execute_query(query)
    return results[0] if results else {}
