import argparse
import datetime as dt
import os
import smtplib
import uuid
from email.message import EmailMessage

from dotenv import load_dotenv
from notte_sdk import NotteClient

SMTP_SERVER_ENV = "SMTP_SERVER"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USERNAME_ENV = "EMAIL_SENDER"
SMTP_PASSWORD_ENV = "EMAIL_PASSWORD"  # pragma: allowlist secret
SMTP_STARTTLS_ENV = "SMTP_STARTTLS"
EMAIL_READ_WINDOW = dt.timedelta(minutes=10)


def send_test_email(recipient: str, subject: str) -> str:
    server = os.environ[SMTP_SERVER_ENV]
    username = os.environ[SMTP_USERNAME_ENV]
    password = os.environ[SMTP_PASSWORD_ENV]
    host, _, server_port = server.partition(":")
    port = int(os.getenv(SMTP_PORT_ENV, server_port or "587"))

    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(f"Notte persona email delivery test: {subject}")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            _ = server.login(username, password)
            _ = server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if os.getenv(SMTP_STARTTLS_ENV, "true").lower() != "false":
                _ = server.starttls()
            _ = server.login(username, password)
            _ = server.send_message(message)

    return username


def main() -> None:
    _ = load_dotenv(".env")

    parser = argparse.ArgumentParser(description="Send an SMTP test email to a Notte persona and read the inbox.")
    _ = parser.add_argument("--persona-id", default=os.getenv("NOTTE_TEST_PERSONA_ID"))
    _ = parser.add_argument(
        "--keep-persona",
        action="store_true",
        help="Keep the temporary persona created by this script. Ignored when --persona-id is set.",
    )
    args = parser.parse_args()

    client = NotteClient()
    created_persona = args.persona_id is None
    persona = (
        client.Persona(create_vault=False, create_phone_number=False)
        if created_persona
        else client.Persona(args.persona_id)
    )

    try:
        subject = f"Notte persona email delivery {uuid.uuid4()}"
        sender = send_test_email(persona.info.email, subject)
        print(f"Sent SMTP email from {sender} to persona {persona.persona_id}: {persona.info.email}")

        emails = persona.emails(only_unread=False, timedelta=EMAIL_READ_WINDOW)
        for email in emails:
            print(
                "email:",
                f"subject={email.subject!r}",
                f"sender={email.sender_email!r}",
                f"created_at={email.created_at.isoformat()}",
            )

        matching_emails = [email for email in emails if email.subject == subject]
        assert matching_emails, f"No fresh SMTP test email found in {len(emails)} emails"
        print(f"Received {len(matching_emails)} matching email(s).")
    finally:
        if created_persona and not args.keep_persona:
            persona.delete()
            print(f"Deleted temporary persona {persona.persona_id}.")


if __name__ == "__main__":
    main()
