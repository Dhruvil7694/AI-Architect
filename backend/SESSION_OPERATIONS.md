# Session operations

## DB session cleanup

When using the default database session backend (no `REDIS_URL`), the `django_session` table grows indefinitely. Run Django’s built-in cleanup daily:

```bash
python manage.py clearsessions
```

Example cron (daily at 03:00):

```cron
0 3 * * * cd /path/to/backend && python manage.py clearsessions
```

## Redis sessions

When `REDIS_URL` is set, sessions are stored in Redis with a TTL of 86400 seconds (24 hours), aligned with `SESSION_COOKIE_AGE`. Stale keys are evicted automatically; no clearsessions job is required for Redis.

## Rate limiting

Login is rate-limited (5 attempts per minute per IP) via `django-ratelimit`. It uses the default cache; for production, use a cache that supports atomic increment (e.g. Redis) so rate limits are consistent across processes.
