from ast import Str
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from pydantic import BaseModel

class EmailConfig(BaseModel):
    """Configuration for email sending functionality."""
    smtp_server: str
    smtp_port: int = 587
    sender_email: str
    sender_password: str
    receiver_email: str
    subject_prefix: str = "[Notte] "
    
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
        msg['From'] = self.config.sender_email
        msg['To'] = self.config.receiver_email
        msg['Subject'] = f"{self.config.subject_prefix}{subject}"
        
        msg.attach(MIMEText(body, 'plain'))
        
        if self._server:
            _ = self._server.send_message(msg)
            
    async def send_completion_email(self, task: str, result: str, success: bool) -> None:
        """Send an email about task completion."""
        status = "completed successfully" if success else "failed"
        subject = f"Task {status}"
        
        body = f"""
            Task: {task}

            Status: {status}

            Result: {result}

            ---
            This is an automated message from Notte
            """
        
        await self.send_email(subject, body)
        
    def __del__(self):
        """Ensure SMTP connection is closed on deletion."""
        if self._server is not None:
            _ = self._server.quit() 