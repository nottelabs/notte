import argparse
import datetime as dt
import os

from dotenv import load_dotenv
from notte_browser.tools.base import PersonaTool
from notte_sdk import NotteClient

import notte

SEND_TEST_MAIL_URL = "https://xeramail.com/send-test-email"
EMAIL_SELECTOR = 'internal:role=textbox[name="Email Address"i]'
SEND_BUTTON_SELECTOR = 'internal:role=button[name="Send Test Email"i]'
EMAIL_DELIVERY_WAIT_MS = 10_000
EMAIL_READ_WINDOW = dt.timedelta(minutes=5)


def main() -> None:
    _ = load_dotenv(".env")

    parser = argparse.ArgumentParser(description="Send a test email to a Notte persona via xeramail.com.")
    _ = parser.add_argument("--persona-id", default=os.getenv("NOTTE_TEST_PERSONA_ID"))
    _ = parser.add_argument(
        "--keep-persona",
        action="store_true",
        help="Keep the temporary persona created by this script. Ignored when --persona-id is set.",
    )
    _ = parser.add_argument("--wait-ms", type=int, default=EMAIL_DELIVERY_WAIT_MS)
    _ = parser.add_argument("--headful", action="store_true", help="Run with a visible browser.")
    args = parser.parse_args()

    client = NotteClient()
    created_persona = args.persona_id is None
    persona = client.Persona() if created_persona else client.Persona(args.persona_id)

    try:
        email = persona.info.email
        started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
        persona_mode = "temporary" if created_persona else "existing"
        print(f"Using {persona_mode} persona {persona.persona_id}: {email}")

        with notte.Session(headless=not args.headful, tools=[PersonaTool(persona)]) as session:
            goto = session.execute(type="goto", url=SEND_TEST_MAIL_URL)
            print(f"goto: success={goto.success} message={goto.message!r}")
            assert goto.success, goto.message

            fill = session.execute(type="fill", selector=EMAIL_SELECTOR, value=email)
            print(f"fill: success={fill.success} message={fill.message!r}")
            assert fill.success, fill.message

            send = session.execute(type="click", selector=SEND_BUTTON_SELECTOR)
            print(f"send: success={send.success} message={send.message!r}")
            assert send.success, send.message

            wait = session.execute(type="wait", time_ms=args.wait_ms)
            assert wait.success, wait.message

            emails = persona.emails(only_unread=False, timedelta=EMAIL_READ_WINDOW)
            print(f"email_read: found {len(emails)} email(s)")
            for email_response in emails:
                print(
                    "email:",
                    f"subject={email_response.subject!r}",
                    f"sender={email_response.sender_email!r}",
                    f"created_at={email_response.created_at.isoformat()}",
                )

            matching_emails = [
                email_response
                for email_response in emails
                if email_response.created_at >= started_at and email_response.sender_email == "test@xeramail.com"
            ]
            assert matching_emails, f"No fresh test email found in {len(emails)} emails"
            print(f"Received {len(matching_emails)} fresh test email(s).")
    finally:
        if created_persona and not args.keep_persona:
            persona.delete()
            print(f"Deleted temporary persona {persona.persona_id}.")


if __name__ == "__main__":
    main()
