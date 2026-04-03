"""
Quick script to create an admin user for testing.
Run: python create_admin.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from users.models import User

# Create admin user
email = "dhruvil7694@gmail.com"
password = "Dp#76001"

if User.objects.filter(email=email).exists():
    print(f"Admin user {email} already exists")
else:
    user = User.objects.create_superuser(
        email=email,
        password=password,
        first_name="Admin",
        last_name="User",
        roles=["admin", "user"],
    )
    print(f"Created admin user: {email}")
    print(f"Password: {password}")

# Create regular user
email2 = "user@example.com"
password2 = "user123"

if User.objects.filter(email=email2).exists():
    print(f"User {email2} already exists")
else:
    user2 = User.objects.create_user(
        email=email2,
        password=password2,
        first_name="Regular",
        last_name="User",
        roles=["user"],
    )
    print(f"Created regular user: {email2}")
    print(f"Password: {password2}")
