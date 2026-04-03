"""
OTP Email Service
Generates, stores, and verifies one-time passwords sent via email.
Uses Django's SMTP email backend configured with Gmail App Password.
"""
import random
import string
from datetime import datetime, timezone, timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache


OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


def generate_otp() -> str:
    """Generate a random numeric OTP."""
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def _cache_key(email: str, purpose: str = "verify") -> str:
    return f"otp:{purpose}:{email.lower()}"


def _attempts_key(email: str, purpose: str = "verify") -> str:
    return f"otp_attempts:{purpose}:{email.lower()}"


def send_otp_email(email: str, purpose: str = "verify") -> bool:
    """
    Generate an OTP, store it in cache, and send it via email.
    Returns True if email was sent successfully.
    """
    otp = generate_otp()
    key = _cache_key(email, purpose)
    attempts_key = _attempts_key(email, purpose)

    # Store OTP with expiry
    cache.set(key, otp, timeout=OTP_EXPIRY_MINUTES * 60)
    # Reset attempts counter
    cache.set(attempts_key, 0, timeout=OTP_EXPIRY_MINUTES * 60)

    # Build email content
    if purpose == "signup":
        subject = "🏗️ AI Architect - Verify Your Email"
        message = (
            f"Welcome to AI Architect!\n\n"
            f"Your verification code is: {otp}\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"If you didn't request this, please ignore this email."
        )
        html_message = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 480px; margin: 0 auto; background: linear-gradient(135deg, #0a0a0a 0%, #141414 50%, #0a0a0a 100%); border-radius: 16px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
            <div style="padding: 40px 32px; text-align: center;">
                <div style="font-size: 28px; font-weight: 700; color: #ffffff; margin-bottom: 8px;">🏗️ AI Architect</div>
                <div style="font-size: 14px; color: #f97316; margin-bottom: 32px;">Verify Your Email Address</div>
                <div style="background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.25); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                    <div style="font-size: 13px; color: #fdba74; margin-bottom: 12px;">Your verification code</div>
                    <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #f97316; font-family: 'Courier New', monospace;">{otp}</div>
                </div>
                <div style="font-size: 13px; color: #9ca3af; line-height: 1.6;">
                    This code expires in <strong style="color: #fdba74;">{OTP_EXPIRY_MINUTES} minutes</strong>.<br>
                    If you didn't request this, please ignore this email.
                </div>
            </div>
            <div style="background: rgba(0,0,0,0.3); padding: 16px 32px; text-align: center;">
                <div style="font-size: 11px; color: #6b7280;">© 2026 AI Architect. All rights reserved.</div>
            </div>
        </div>
        """
    else:
        subject = "🔐 AI Architect - Login Verification"
        message = (
            f"Your login verification code is: {otp}\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"If you didn't request this, please ignore this email."
        )
        html_message = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 480px; margin: 0 auto; background: linear-gradient(135deg, #0a0a0a 0%, #141414 50%, #0a0a0a 100%); border-radius: 16px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
            <div style="padding: 40px 32px; text-align: center;">
                <div style="font-size: 28px; font-weight: 700; color: #ffffff; margin-bottom: 8px;">🔐 AI Architect</div>
                <div style="font-size: 14px; color: #f97316; margin-bottom: 32px;">Login Verification</div>
                <div style="background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.25); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                    <div style="font-size: 13px; color: #fdba74; margin-bottom: 12px;">Your verification code</div>
                    <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #f97316; font-family: 'Courier New', monospace;">{otp}</div>
                </div>
                <div style="font-size: 13px; color: #9ca3af; line-height: 1.6;">
                    This code expires in <strong style="color: #fdba74;">{OTP_EXPIRY_MINUTES} minutes</strong>.<br>
                    If you didn't request this, please ignore this email.
                </div>
            </div>
            <div style="background: rgba(0,0,0,0.3); padding: 16px 32px; text-align: center;">
                <div style="font-size: 11px; color: #6b7280;">© 2026 AI Architect. All rights reserved.</div>
            </div>
        </div>
        """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"[OTP] Failed to send email to {email}: {e}")
        return False


def verify_otp(email: str, otp: str, purpose: str = "verify") -> tuple[bool, str]:
    """
    Verify an OTP for a given email.
    Returns (success, message).
    """
    key = _cache_key(email, purpose)
    attempts_key = _attempts_key(email, purpose)

    stored_otp = cache.get(key)

    if stored_otp is None:
        return False, "OTP has expired or was not requested. Please request a new one."

    # Check attempts
    attempts = cache.get(attempts_key, 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        cache.delete(key)
        cache.delete(attempts_key)
        return False, "Too many failed attempts. Please request a new OTP."

    if stored_otp != otp:
        cache.set(attempts_key, attempts + 1, timeout=OTP_EXPIRY_MINUTES * 60)
        remaining = OTP_MAX_ATTEMPTS - attempts - 1
        return False, f"Invalid OTP. {remaining} attempt(s) remaining."

    # Success — clean up
    cache.delete(key)
    cache.delete(attempts_key)
    return True, "OTP verified successfully."
