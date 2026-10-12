# @sniptest filename=param_notifier.py
# @sniptest show=1-18
# Requires the integrations package: pip install "notte[integrations]"
from notte_integrations.notifiers.mail import EmailConfig, EmailNotifier
from notte_sdk import NotteClient

client = NotteClient()

notifier = EmailNotifier(
    config=EmailConfig(
        smtp_server="smtp.example.com",
        sender_email="agent@example.com",
        sender_password="your-smtp-password",
        receiver_email="you@example.com",
    )
)

with client.Session() as session:
    # Sends an email with the result when the agent finishes
    agent = client.Agent(session=session, notifier=notifier)
    status = session.status()
    assert agent.request.notifier_config is not None
    assert agent.request.session_id == status.session_id
