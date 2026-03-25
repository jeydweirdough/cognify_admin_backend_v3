import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr  # <-- This is the missing import that caused the error!
from fastapi import BackgroundTasks

def send_email_sync(to_email: str, subject: str, html_content: str):
    """Synchronous function to send an email via SMTP."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)
    from_name = os.getenv("FROM_NAME", "CVSU-B Cognify Admin")  # Gets the name from .env

    if not smtp_user or not smtp_pass:
        print(f"[Email Skipped] Missing SMTP credentials. Would have sent to: {to_email}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    
    # Formats the sender as: "CVSU-B Cognify Admin <your.email@gmail.com>"
    msg["From"] = formataddr((from_name, from_email)) 
    
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[Email Success] Sent to {to_email}")
    except Exception as e:
        print(f"[Email Error] Failed to send to {to_email}: {e}")

def queue_email(background_tasks: BackgroundTasks, to_email: str, subject: str, html_content: str):
    """Queues the email to be sent in the background."""
    if to_email:
        background_tasks.add_task(send_email_sync, to_email, subject, html_content)