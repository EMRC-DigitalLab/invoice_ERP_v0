#!/usr/bin/env python3
"""
Manually apply the Invoice Submitter Form schema migration.

Not required in normal operation — app.main.lifespan already runs
app.core.migrations.run_pending_migrations() on every startup, so a fresh
deploy applies this automatically. This script exists only for someone who
wants to apply it ahead of a deploy, e.g. against a local/dev database:

    python scripts/migrate_invoice_submitter_fields.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from app.core.migrations import run_pending_migrations


def main() -> None:
    run_pending_migrations(engine)
    print("Migration applied successfully.")


if __name__ == "__main__":
    main()
