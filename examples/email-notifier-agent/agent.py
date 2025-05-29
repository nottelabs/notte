import os

from dotenv import load_dotenv
from notte_integrations.notifiers.mail import EmailConfig, EmailNotifier
from notte_sdk import NotteClient

# Load environment variables
_ = load_dotenv()


notte = NotteClient()


# Create the EmailConfig
def main():
    notifier = EmailNotifier(
        config=EmailConfig(
            smtp_server=str(os.environ["SMTP_SERVER"]),
            sender_email=str(os.environ["EMAIL_SENDER"]),
            sender_password=str(os.environ["EMAIL_PASSWORD"]),
            receiver_email=str(os.environ["EMAIL_RECEIVER"]),
        )
    )
    with notte.Session(headless=False) as session:
        notifier_agent = notte.Agent(notifier=notifier, session=session)

        response = notifier_agent.run(task="Make a summary of the financial times latest news")

    if not response.success:
        exit(-1)


if __name__ == "__main__":
    main()
