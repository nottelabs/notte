# @sniptest filename=param_notifier.py
# @sniptest show=4-17
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Sends an email with the result when the agent finishes
    agent = client.Agent(
        session=session,
        notifier_config={
            "type": "email",
            "config": {
                "smtp_server": "smtp.example.com",
                "sender_email": "agent@example.com",
                "sender_password": "your-smtp-password",
                "receiver_email": "you@example.com",
            },
        },
    )
    status = session.status()
    assert agent.request.notifier_config is not None
    assert agent.request.session_id == status.session_id
status = client.sessions.status(agent.request.session_id)
