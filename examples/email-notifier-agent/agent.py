import os

from dotenv import load_dotenv
from notte_agent import Agent

from notte_integrations.notifiers.mail import EmailNotifier

# Load environment variables
_ = load_dotenv()


# Create the EmailConfig
def main():
    notifier = EmailNotifier(
        smtp_server=str(os.getenv("SMTP_SERVER")),
        sender_email=str(os.getenv("EMAIL_SENDER")),
        sender_password=str(os.getenv("EMAIL_PASSWORD")),
        receiver_email=str(os.getenv("EMAIL_RECEIVER")),
    )
    notifier_agent = Agent(notifier=notifier)
    response = notifier_agent.run("Make a summary of the financial times latest news")
    print(response)


if __name__ == "__main__":
    main()
