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
    # Indexes for the columns list_requests/get_summary filter and sort on —
    # create_all() only indexes tables at creation time, so existing
    # deployments need these added explicitly. Names match the ix_<table>_<col>
    # convention SQLAlchemy would generate for a fresh table.
    "CREATE INDEX IF NOT EXISTS ix_requests_status ON requests (status);",
    "CREATE INDEX IF NOT EXISTS ix_requests_type ON requests (type);",
    "CREATE INDEX IF NOT EXISTS ix_requests_requested_by_id ON requests (requested_by_id);",
    "CREATE INDEX IF NOT EXISTS ix_requests_created_at ON requests (created_at);",
    # Job Type (Work/Service) + a free-text Description, added to the Invoice
    # Submitter Form alongside the existing Subject/"Invoice-Service Title".
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS job_type VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS description VARCHAR;",
    # Same Job Type field, plus the contractor's address, captured on the PO
    # itself so it doesn't need re-entering on every request against it.
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS job_type VARCHAR;",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS contractor_address VARCHAR;",
    # Indexes for PO list/CSV-export filters and, more importantly, for
    # committed_amount_for_po() — it filters requests.po_id once per PO row
    # shown, so an unindexed po_id turns every PO list/export into N table
    # scans of requests as either table grows.
    "CREATE INDEX IF NOT EXISTS ix_purchase_orders_status ON purchase_orders (status);",
    "CREATE INDEX IF NOT EXISTS ix_purchase_orders_job_type ON purchase_orders (job_type);",
    "CREATE INDEX IF NOT EXISTS ix_requests_po_id ON requests (po_id);",
    # "Seek Further Clarification" — CFO sends a secure, tokenised link to an
    # external respondent by email; the clarification_requests table itself is
    # created by Base.metadata.create_all() (it's a new table), so these just
    # add the lookup indexes create_all() only sets up at table-creation time.
    "CREATE INDEX IF NOT EXISTS ix_clarification_requests_request_id ON clarification_requests (request_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_clarification_requests_token ON clarification_requests (token);",
    # Optional message the CFO can attach when seeking clarification, added
    # after clarification_requests already existed in some environments.
    "ALTER TABLE clarification_requests ADD COLUMN IF NOT EXISTS note VARCHAR;",
    # "Forward" — the CFO can route a request to a specific person (e.g. the
    # MD) as an extra approval step ahead of them, instead of just role-based
    # resolution.
    "ALTER TABLE approval_steps ADD COLUMN IF NOT EXISTS assigned_user_id VARCHAR;",
    # MD is now a proper org-wide singular seat (like CFO/Finance Controller),
    # resolved the same way rather than only reachable via ad-hoc "Forward".
    "ALTER TABLE org_settings ADD COLUMN IF NOT EXISTS md_user_id VARCHAR;",
    # "Requesting Department" on Cash Advance / State of Expense / IOU — a
    # fixed-list pick (Regulatory, F&A, etc.), not tied to the Department
    # org-directory table/routing.
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS requesting_department VARCHAR;",
    # Memo Request — a new request type with a narrative body + optional CC
    # line, plus a variable-length officer/line-items table (memo_line_items,
    # a new table created by create_all()) rather than fixed columns.
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS memo_body VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS memo_cc VARCHAR;",
    "CREATE INDEX IF NOT EXISTS ix_memo_line_items_request_id ON memo_line_items (request_id);",
    # Memo line items were first modeled on a single hotel-accommodation memo
    # (officer/nights/rate-per-night) — generalized to description/quantity/
    # unit_rate so the table fits any memo type, not just that one.
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'memo_line_items' AND column_name = 'officer_name')
           AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'memo_line_items' AND column_name = 'description')
        THEN
            ALTER TABLE memo_line_items RENAME COLUMN officer_name TO description;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'memo_line_items' AND column_name = 'nights')
           AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'memo_line_items' AND column_name = 'quantity')
        THEN
            ALTER TABLE memo_line_items RENAME COLUMN nights TO quantity;
        END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'memo_line_items' AND column_name = 'rate_per_night')
           AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'memo_line_items' AND column_name = 'unit_rate')
        THEN
            ALTER TABLE memo_line_items RENAME COLUMN rate_per_night TO unit_rate;
        END IF;
    END $$;
    """,
    "ALTER TABLE memo_line_items ALTER COLUMN quantity TYPE FLOAT USING quantity::float;",
    # Retention/holdback on the Invoice Submitter Form — percentage or fixed
    # amount withheld from the invoice payment, per the CFO's request.
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS retention_type VARCHAR;",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS retention_value FLOAT;",
]


def run_pending_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _STATEMENTS:
            conn.execute(text(stmt))
