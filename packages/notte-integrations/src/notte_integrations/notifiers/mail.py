import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Annotated

from notte_agent.common.notifier import BaseNotifier
from pydantic import BaseModel, Field
from typing_extensions import override


class EmailConfig(BaseModel):
    """Configuration for email sending functionality."""

    smtp_server: Annotated[str, Field(min_length=1)]
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 587
    sender_email: Annotated[str, Field(min_length=1)]
    sender_password: Annotated[str, Field(min_length=1)]
    receiver_email: Annotated[str, Field(min_length=1)]
    subject: str = "Notte Agent Task Report"


class EmailNotifier(BaseNotifier):
    """Email notification implementation."""

    def __init__(self, config: EmailConfig) -> None:
        super().__init__()  # Call parent class constructor
        self.config: EmailConfig = config
        self._server: smtplib.SMTP | None = None

    def connect(self) -> None:
        """Connect to the SMTP server."""
        if self._server is not None:
            return

        self._server = smtplib.SMTP(host=self.config.smtp_server, port=self.config.smtp_port)
        _ = self._server.starttls()
        _ = self._server.login(user=self.config.sender_email, password=self.config.sender_password)

    def disconnect(self) -> None:
        """Disconnect from the SMTP server."""
        if self._server is not None:
            _ = self._server.quit()
            self._server = None

    @override
    def send_message(self, text: str) -> None:
        """Send an email with the given subject and body."""
        self.connect()
        try:
            if self._server is None:
                self.connect()

            msg = MIMEMultipart()
            msg["From"] = self.config.sender_email
            msg["To"] = self.config.receiver_email
            msg["Subject"] = self.config.subject

            msg.attach(MIMEText(text, "plain"))

            if self._server:
                _ = self._server.send_message(msg)
        finally:
            self.disconnect()

    def __del__(self):
        """Ensure SMTP connection is closed on deletion."""
        if self._server is not None:
            _ = self._server.quit()
