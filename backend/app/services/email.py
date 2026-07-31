import base64
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import models
from app.config import settings


def _crypto() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_smtp_password(value: str) -> str:
    return _crypto().encrypt(value.encode()).decode()


def decrypt_smtp_password(token: str) -> str:
    return _crypto().decrypt(token.encode()).decode()


async def get_smtp_config(db: AsyncSession) -> dict:
    keys = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_use_tls"]
    values = {}
    for key in keys:
        s = await db.execute(select(models.SiteSetting).where(models.SiteSetting.key == key))
        row = s.scalar_one_or_none()
        values[key] = row.value if row else None
    try:
        port = int(values["smtp_port"]) if values.get("smtp_port") else 587
    except (ValueError, TypeError):
        port = 587
    password = decrypt_smtp_password(values["smtp_password"]) if values.get("smtp_password") else None
    return {
        "host": values.get("smtp_host"),
        "port": port,
        "user": values.get("smtp_user"),
        "password": password,
        "from_address": values.get("smtp_from") or values.get("smtp_user"),
        "use_tls": (values.get("smtp_use_tls", "true") or "true").lower() != "false",
        "configured": bool(values.get("smtp_host") and values.get("smtp_user") and password),
    }


async def send_email(
    db: AsyncSession,
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> None:
    cfg = await get_smtp_config(db)
    if not cfg["configured"]:
        raise RuntimeError("SMTP is not configured")
    context = ssl.create_default_context()
    if cfg["use_tls"]:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        server.starttls(context=context)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
    server.login(cfg["user"], cfg["password"])
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"]
    msg["To"] = to
    if html:
        msg.set_content(body)
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(body)
    server.send_message(msg)
    server.quit()
