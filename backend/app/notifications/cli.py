# backend/app/notifications/cli.py
from app.notifications.jobs import run_notifications


def main() -> None:
    result = run_notifications()
    print(f"Linked {result['linked']} Telegram account(s), sent {result['sent']} notification(s)")


if __name__ == "__main__":
    main()
