import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Annotated, Literal

from notte_core.common.notifier import BaseNotifier
from pydantic import BaseModel, Field
from typing_extensions import override

DEFAULT_SMTP_PORT = 587


class EmailConfig(BaseModel):
    """Configuration for email sending functionality."""

    smtp_server: Annotated[str, Field(min_length=1)]
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = DEFAULT_SMTP_PORT
    sender_email: Annotated[str, Field(min_length=1)]
    sender_password: Annotated[str, Field(min_length=1)]
    receiver_email: Annotated[str, Field(min_length=1)]
    subject: str = "Notte Agent Task Report"


class EmailNotifier(BaseNotifier):
    """Email notification implementation."""

    type: Literal["email"] = "email"  # pyright: ignore [reportIncompatibleVariableOverride]
    config: EmailConfig
    server: smtplib.SMTP | None = Field(exclude=True, default=None)

    def connect(self) -> None:
        """Connect to the SMTP server."""
        if self.server is not None:
            return

        self.server = smtplib.SMTP(host=self.config.smtp_server, port=self.config.smtp_port)
        _ = self.server.starttls()
        _ = self.server.login(user=self.config.sender_email, password=self.config.sender_password)

    def disconnect(self) -> None:
        """Disconnect from the SMTP server."""
        if self.server is not None:
            _ = self.server.quit()
            self.server = None

    @override
    def send_message(self, text: str) -> None:
        """Send an email with the given subject and body."""
        self.connect()
        try:
            if self.server is None:
                self.connect()

            msg = MIMEMultipart()
            msg["From"] = self.config.sender_email
            msg["To"] = self.config.receiver_email
            msg["Subject"] = self.config.subject

            msg.attach(MIMEText(text, "plain"))

            if self.server:
                _ = self.server.send_message(msg)
        finally:
            self.disconnect()

    def __del__(self):
        """Ensure SMTP connection is closed on deletion."""
        if self.server is not None:
            _ = self.server.quit()
