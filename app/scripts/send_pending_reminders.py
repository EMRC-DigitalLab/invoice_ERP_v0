"""
Manual, on-demand trigger for the same pending-approval reminder sweep the
daily scheduler runs (app/core/scheduler.py) — useful for checking right now
without waiting for the next 07:00 UTC run. Threshold and test-email
override are controlled by PENDING_REMINDER_THRESHOLD / PENDING_REMINDER_TEST_EMAIL
in settings, not hardcoded here, so this always reflects the same config the
scheduler uses.

Run inside the API container:
    docker compose exec api python -m app.scripts.send_pending_reminders
"""

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.pending_reminders import run_reminder_sweep


def main() -> None:
    db = SessionLocal()
    try:
        results = run_reminder_sweep(db)
        if not results:
            print("No users found for the configured reminder roles.")
            return

        for user, count in results:
            if count >= settings.PENDING_REMINDER_THRESHOLD:
                recipient = settings.PENDING_REMINDER_TEST_EMAIL or user.email
                print(
                    f"{user.name} ({user.email}): {count} pending — reminder sent to {recipient}."
                )
            else:
                print(
                    f"{user.name} ({user.email}): {count} pending — under threshold ({settings.PENDING_REMINDER_THRESHOLD}), no email sent."
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
