from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication"""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.
    Uses email as the primary identifier.
    """
    email = models.EmailField(unique=True)
    
    # Override username to make it optional
    username = models.CharField(max_length=150, blank=True, null=True)
    
    # Additional fields
    roles = models.JSONField(default=list, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
    
    def __str__(self):
        return self.email
    
    @property
    def name(self):
        """Return full name or email prefix"""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email.split("@")[0]


class Notification(models.Model):
    """
    Model for storing user notifications.
    Categories: success, info, warning, error, ai_render
    """
    TYPES = [
        ('success', 'Success'),
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('ai_render', 'AI Rendering'),
    ]

    id = models.UUIDField(primary_key=True, default=None, editable=False) # Will use uuid.uuid4 in actual save
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        import uuid
        if not self.id:
            self.id = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.title}"

