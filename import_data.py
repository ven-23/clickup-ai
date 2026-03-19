import telemetry
import pandas as pd
import numpy as np
import psycopg2
from sqlalchemy import create_engine, text
import os
from datetime import datetime
from dotenv import load_dotenv
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database connection details
DB_URL = os.getenv("DB_URL", "postgresql://clickup_user:clickup_pass@localhost:5433/clickup_db")

# CSV File paths - Configurable via ENV for Docker
CSV_FILES = [
    os.getenv("CSV_FILE_1", "data/Mar-Jul2025.csv"),
    os.getenv("CSV_FILE_2", "data/Sep-Jan.csv")
]

def clean_data(df):
    """Surgical cleaning: Defensive processing to ensure no crashes during large imports."""
    column_mapping = {
        'User ID': 'user_id',
        'Username': 'username',
        'Time Entry ID': 'time_entry_id',
        'Description': 'description',
        'Billable': 'billable',
        'Time Labels': 'time_labels',
        'Start': 'start_time',
        'Stop': 'stop_time',
        'Time Tracked': 'time_tracked_ms',
        'Space ID': 'space_id',
        'Space Name': 'space_name',
        'Folder ID': 'folder_id',
        'Folder Name': 'folder_name',
        'List ID': 'list_id',
        'List Name': 'list_name',
        'Task ID': 'task_id',
        'Task Name': 'task_name',
        'Task Status': 'task_status',
        'Due Date': 'due_date',
        'Start Date': 'start_date',
        'Task Time Estimated': 'task_time_estimated',
        'Task Time Spent': 'task_time_spent',
        'User Total Time Estimated': 'user_total_time_estimated',
        'User Total Time Tracked': 'user_total_time_tracked',
        'Tags': 'tags',
        'Checklists': 'checklists',
        'User Period Time Spent': 'user_period_time_spent',
        'Date Created': 'date_created',
        'Custom Task ID': 'custom_task_id',
        'Parent Task ID': 'parent_task_id',
        'Hours to Bill': 'hours_to_bill',
        'On Track': 'on_track',
        'Retainer Hours Left': 'retainer_hours_left',
        'Time Remaining': 'time_remaining',
        'Agency (If multiple, please reach out to the Admin team for the breakdown of hours)': 'agency_name',
        'Client': 'client_project_name',
        'Job Number': 'job_number',
        'BRIEF': 'brief',
        'Billed': 'billed',
        'Billing Notes': 'billing_notes',
        'Client Name - Project Contact': 'client_contact',
        'Days Left': 'days_left',
        'Fixed quoted hours': 'fixed_quoted_hours',
        'How is this job being billed?': 'billing_method',
        'Invoice Method': 'invoice_method',
        'Invoice No': 'invoice_no',
        'Job Type': 'job_type',
        'Project Identifier': 'project_identifier',
        'Project Manager': 'project_manager',
        'Requestor': 'requestor',
        'Urgency': 'urgency',
        'Billable Hours Instruction (copy)': 'billing_instructions',
        'Billing Cycle (2)': 'billing_cycle',
        'Additional Agency Division': 'agency_division',
        'Additional Notes': 'additional_notes',
        'Pre Paid Bundle': 'pre_paid_bundle',
        'New or Existing Client': 'client_type',
        'Smoko': 'smoko',
        'Time Remaining (R)': 'time_remaining_r',
        'Traffic (%)': 'traffic_percent',
        'Bundle Discounted Rate': 'bundle_discount_rate',
        'Client Approval Name': 'client_approval_name',
        'Prepaid Hours': 'prepaid_hours',
        'Login Credentials': 'login_credentials',
        'PO Number': 'po_number'
    }

    avail_cols = [c for c in column_mapping.keys() if c in df.columns]
    df_filtered = df[avail_cols].copy().rename(columns=column_mapping)

    # Convert booleans
    bool_cols = ['billable', 'billed', 'on_track', 'smoko']
    for col in bool_cols:
        if col in df_filtered.columns:
            try:
                s = df_filtered[col].astype(str).str.lower().str.strip()
                df_filtered[col] = s.map({
                    'true': True, '1': True, '1.0': True, 'yes': True,
                    'false': False, '0': False, '0.0': False, 'no': False,
                    'nan': False, 'none': False, '': False
                }).fillna(False).astype(bool)
            except Exception:
                df_filtered[col] = False

    # Clean character names
    name_cols = ['username', 'project_manager', 'requestor', 'client_approval_name']
    for col in name_cols:
        if col in df_filtered.columns:
            try:
                df_filtered[col] = df_filtered[col].astype(str).str.replace(r'\[|\]', '', regex=True).str.strip()
                df_filtered[col] = df_filtered[col].replace(['nan', 'None', ''], None)
            except Exception:
                pass

    # Convert unix timestamps (ms) to datetime
    ts_cols = ['start_time', 'stop_time', 'date_created', 'due_date', 'start_date']
    for col in ts_cols:
        if col in df_filtered.columns:
            try:
                # Use a very safe nested conversion
                num_ts = pd.to_numeric(df_filtered[col], errors='coerce')
                df_filtered[col] = pd.to_datetime(num_ts, unit='ms', utc=True)
            except Exception:
                df_filtered[col] = pd.NaT

    # Convert numeric fields
    num_cols = [
        'time_tracked_ms', 'task_time_estimated', 'task_time_spent', 
        'user_total_time_estimated', 'user_total_time_tracked', 
        'user_period_time_spent', 'hours_to_bill', 'retainer_hours_left', 
        'time_remaining', 'days_left', 'fixed_quoted_hours', 
        'traffic_percent', 'bundle_discount_rate', 'prepaid_hours'
    ]
    for col in num_cols:
        if col in df_filtered.columns:
            try:
                df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')
                # fillna(0) only if strictly numeric to avoid fromnumeric errors
                df_filtered[col] = df_filtered[col].where(df_filtered[col].notnull(), 0)
            except Exception:
                df_filtered[col] = 0

    return df_filtered

def main():
    logger.info("Connecting to database...")
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        logger.info("Enabling extensions and creating enriched schema...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;"))
        
        conn.execute(text("""
            DROP TABLE IF EXISTS time_entries CASCADE;
            CREATE TABLE time_entries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                time_entry_id BIGINT,
                description TEXT,
                billable BOOLEAN,
                time_labels TEXT,
                start_time TIMESTAMPTZ,
                stop_time TIMESTAMPTZ,
                time_tracked_ms BIGINT,
                space_id TEXT,
                space_name TEXT,
                folder_id TEXT,
                folder_name TEXT,
                list_id TEXT,
                list_name TEXT,
                task_id TEXT,
                task_name TEXT,
                task_status TEXT,
                due_date TIMESTAMPTZ,
                start_date TIMESTAMPTZ,
                task_time_estimated BIGINT,
                task_time_spent BIGINT,
                user_total_time_estimated BIGINT,
                user_total_time_tracked BIGINT,
                tags JSONB,
                checklists TEXT,
                user_period_time_spent BIGINT,
                date_created TIMESTAMPTZ,
                custom_task_id TEXT,
                parent_task_id TEXT,
                hours_to_bill NUMERIC,
                on_track BOOLEAN,
                retainer_hours_left NUMERIC,
                time_remaining NUMERIC,
                agency_name TEXT,
                client_project_name TEXT,
                job_number TEXT,
                brief TEXT,
                billed BOOLEAN,
                billing_notes TEXT,
                client_contact TEXT,
                days_left NUMERIC,
                fixed_quoted_hours NUMERIC,
                billing_method TEXT,
                invoice_method TEXT,
                invoice_no TEXT,
                job_type TEXT,
                project_identifier TEXT,
                project_manager TEXT,
                requestor TEXT,
                urgency TEXT,
                billing_instructions TEXT,
                billing_cycle TEXT,
                agency_division TEXT,
                additional_notes TEXT,
                pre_paid_bundle TEXT,
                client_type TEXT,
                smoko BOOLEAN,
                time_remaining_r TEXT,
                traffic_percent NUMERIC,
                bundle_discount_rate NUMERIC,
                client_approval_name TEXT,
                prepaid_hours NUMERIC,
                login_credentials TEXT,
                po_number TEXT
            );
            
            -- High-Performance Trigram Indexes for Fuzzy Search
            CREATE INDEX idx_entries_username_trgm ON time_entries USING gin(username gin_trgm_ops);
            CREATE INDEX idx_entries_task_name_trgm ON time_entries USING gin(task_name gin_trgm_ops);
            CREATE INDEX idx_entries_client_trgm ON time_entries USING gin(client_project_name gin_trgm_ops);
            CREATE INDEX idx_entries_agency_trgm ON time_entries USING gin(agency_name gin_trgm_ops);
            CREATE INDEX idx_entries_pm_trgm ON time_entries USING gin(project_manager gin_trgm_ops);
            
            -- Standard B-Tree indexes for exact/range matching
            CREATE INDEX idx_entries_start ON time_entries(start_time);
            CREATE INDEX idx_entries_task_id ON time_entries(task_id);
            CREATE INDEX idx_entries_job_no ON time_entries(job_number);
        """))
        conn.commit()

    for csv_path in CSV_FILES:
        logger.info(f"Processing {os.path.basename(csv_path)}...")
        chunksize = 5000 
        for i, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunksize, low_memory=False)):
            logger.info(f"  Cleaning chunk {i+1}...")
            cleaned_chunk = clean_data(chunk)
            cleaned_chunk.to_sql('time_entries', engine, if_exists='append', index=False)
            logger.info(f"  Uploaded chunk {i+1} ({len(cleaned_chunk)} rows).")

    logger.info("Data import complete!")

if __name__ == "__main__":
    main()
