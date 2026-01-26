# @sniptest filename=webhook_handler.py
# @sniptest show=9-19


def process_order(data: dict) -> None:
    print(f"Processing order: {data}")


def send_welcome_email(data: dict) -> None:
    print(f"Sending welcome email: {data}")


def run(event_type: str, data: dict):
    """Handle webhook events."""
    if event_type == "order.created":
        # Process new order
        process_order(data)
    elif event_type == "user.signup":
        # Welcome new user
        send_welcome_email(data)

    return {"status": "processed", "event": event_type}
