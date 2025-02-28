import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pydantic import BaseModel
from typing_extensions import override

from notte.common.agent.types import AgentResponse
from notte.common.notifier.base import BaseNotifier


class EmailConfig(BaseModel):
    """Configuration for email sending functionality."""

    smtp_server: str
    smtp_port: int = 587
    sender_email: str
    sender_password: str
    receiver_email: str


class EmailService:
    """Service for sending emails from Notte."""

    def __init__(self, config: EmailConfig):
        self.config: EmailConfig = config
        self._server: smtplib.SMTP | None = None

    async def connect(self) -> None:
        """Connect to the SMTP server."""
        if self._server is not None:
            return

        self._server = smtplib.SMTP(host=self.config.smtp_server, port=self.config.smtp_port)
        _ = self._server.starttls()
        _ = self._server.login(user=self.config.sender_email, password=self.config.sender_password)

    async def disconnect(self) -> None:
        """Disconnect from the SMTP server."""
        if self._server is not None:
            _ = self._server.quit()
            self._server = None

    async def send_email(self, subject: str, body: str) -> None:
        """Send an email with the given subject and body."""
        if self._server is None:
            await self.connect()

        msg = MIMEMultipart()
        msg["From"] = self.config.sender_email
        msg["To"] = self.config.receiver_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        if self._server:
            _ = self._server.send_message(msg)

    def __del__(self):
        """Ensure SMTP connection is closed on deletion."""
        if self._server is not None:
            _ = self._server.quit()


class EmailNotifier(BaseNotifier):
    """Email notification implementation."""

    def __init__(self, config: EmailConfig) -> None:
        super().__init__()  # Call parent class constructor
        self.email_service: EmailService = EmailService(config)

    @override
    async def notify(self, task: str, result: AgentResponse) -> None:
        """Send an email notification about the task result.

        Args:
            task: The task description
            result: The agent's response to be sent
        """
        await self.email_service.connect()
        try:
            subject = "Notte agent response"  # Use the task in the subject
            await self.email_service.send_email(subject, body=result.answer)
        finally:
            await self.email_service.disconnect()
