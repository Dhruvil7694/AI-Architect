import django
from django.conf import settings

# Ensure Django is set up before any test imports
if not settings.configured:
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    django.setup()
