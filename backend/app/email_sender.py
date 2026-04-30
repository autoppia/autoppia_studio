import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "smtp").strip().lower()
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USERNAME = os.getenv("EMAIL_HOST_USERNAME")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


class EmailSender:
    def send_email(self, to_email: str, subject: str, message: str) -> None:
        if EMAIL_BACKEND == "console":
            logger.warning(
                "[EMAIL_BACKEND=console] To=%s | %s | %s",
                to_email,
                subject,
                message,
            )
            return

        from_email = EMAIL_HOST_USERNAME
        from_password = EMAIL_HOST_PASSWORD
        if not from_email or not from_password:
            raise RuntimeError("Missing EMAIL_HOST_USERNAME or EMAIL_HOST_PASSWORD env vars. For local testing set EMAIL_BACKEND=console in .env (OTP is logged here).")

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(message, "plain"))

        server = smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT)
        server.login(from_email, from_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent to {to_email}: {subject}")
