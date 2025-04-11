import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.notifier.base import NotifierAgent
from notte.common.notifier.mail import EmailConfig, EmailNotifier

# Load environment variables
_ = load_dotenv()

# Configure email notifier
smtp_server = os.getenv("SMTP_SERVER")
smtp_port = os.getenv("SMTP_PORT")
sender_email = os.getenv("EMAIL_SENDER")
sender_password = os.getenv("EMAIL_PASSWORD")
receiver_email = os.getenv("EMAIL_RECEIVER")

# Check for required environment variables
if not smtp_server or not smtp_port or not sender_email or not sender_password or not receiver_email:
    raise ValueError("SMTP_SERVER, SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER")

# Convert smtp_port to int, providing a default if necessary
try:
    smtp_port = int(smtp_port)
except ValueError:
    raise ValueError(f"SMTP_PORT must be an integer, but got: {smtp_port}")

# Create the EmailConfig
email_config = EmailConfig(
    smtp_server=smtp_server,
    smtp_port=smtp_port,
    sender_email=sender_email,
    sender_password=sender_password,
    receiver_email=receiver_email,
)

notifier = EmailNotifier(email_config)

# Configure the agent
config = AgentConfig().cerebras().map_env(lambda env: env.not_headless().steps(15).disable_web_security())
notifier_agent = NotifierAgent(Agent(config=config), notifier)


async def main():
    return await notifier_agent.run(
        ("Make a summary of the financial times latest news"),
    )


if __name__ == "__main__":
    response = asyncio.run(main())
    print(response)


# Run the async function
