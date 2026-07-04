"""
Hand-rolled schema migrations — this repo has no Alembic. Statements here run
automatically on every app startup (see app.main.lifespan), right after
Base.metadata.create_all(), which only creates missing tables and can't alter
existing columns. Keep every statement idempotent (IF EXISTS / IF NOT EXISTS).
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Invoice Submitter Form schema (per the CFO's 2026-07 review call — was
# "Procurement Form"): renames vendor_name -> contractor_name preserving
# data, drops vendor bank/account + old project fields, adds the new
# Invoice Submitter Form fields and the approval "reservation" decision flag.
_STATEMENTS = [
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'requests' AND column_name = 'vendor_name')
           AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'requests' AND column_name = 'contractor_name')
        THEN
            ALTER TABLE requests RENAME COLUMN vendor_name TO contractor_name;
        END IF;
    END $$;
    """,
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS contractor_name VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS service_order_name VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS invoice_number VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS invoice_date VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS payment_timeframe_days INTEGER;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS payment_option VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS tin VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS service_status VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS documents_confirmed BOOLEAN NOT NULL DEFAULT FALSE;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS vendor_bank_name;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS vendor_account_name;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS vendor_account_no;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS project_start_date;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS total_project_sum;",
    "ALTER TABLE requests DROP COLUMN IF EXISTS project_kind;",
    "ALTER TABLE approval_steps ADD COLUMN IF NOT EXISTS reservation BOOLEAN;",
    # E-signature capture was replaced by an automatic name+timestamp record
    # (already tracked via acted_by_name/acted_at) — no drawn signature needed.
    "ALTER TABLE approval_steps DROP COLUMN IF EXISTS signature;",
    # Purchase order lookup — the purchase_orders table itself is created by
    # Base.metadata.create_all() (it's a new table); this just links requests to it.
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS po_id VARCHAR;",
]


def run_pending_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _STATEMENTS:
            conn.execute(text(stmt))
