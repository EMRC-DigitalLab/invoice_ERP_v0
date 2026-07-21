"""
Manual, on-demand trigger for the same decision-digest sweep the scheduler
runs every 3 hours (app/core/scheduler.py) — useful for checking right now
without waiting for the next scheduled run.

Run inside the API container:
    docker compose exec api python -m app.scripts.send_decision_digests
"""

from app.core.database import SessionLocal
from app.services.decision_digest import run_decision_digest_sweep


def main() -> None:
    db = SessionLocal()
    try:
        results = run_decision_digest_sweep(db)
        if not results:
            print("No queued decision notifications.")
            return

        for result in results:
            print(
                f"{result.recipient_email}: {result.queued_count} queued, "
                f"{result.emails_sent} digest email(s) sent."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
