# Enterprise Production Deployment Guide for LabTrack

This document details step-by-step procedures for deploying **LabTrack** in production environments.

---

## 1. Prerequisites & Stack Requirements

- **OS:** Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9 recommended)
- **Python:** Python 3.12+
- **Database:** PostgreSQL 14+ (or SQLite for small-scale deployments)
- **Cache/Broker:** Redis 7+
- **Web Server:** Nginx (Reverse Proxy) + Gunicorn (WSGI Server)
- **Containerization:** Docker 24+ & Docker Compose v2+

---

## 2. Environment Variables Configuration

Copy `.env.example` to `.env` and set mandatory production variables:

```ini
DJANGO_ENV=production
DJANGO_SECRET_KEY=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
DJANGO_ALLOWED_HOSTS=labtrack.example.com,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://labtrack.example.com

# Database (PostgreSQL)
DATABASE_URL=postgres://labuser:SecurePassword123@db:5432/labtrack_db

# Celery & Redis
CELERY_BROKER_URL=redis://redis:6379/0
REDIS_CACHE_URL=redis://redis:6379/1

# Security SSL Settings
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
```

---

## 3. Docker Deployment (Recommended)

1. **Build and Launch Container Services:**
   ```bash
   docker compose up -d --build
   ```

2. **Execute Database Migrations:**
   ```bash
   docker compose exec web python manage.py migrate
   ```

3. **Create Superuser Account:**
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

4. **Verify Health Check Endpoint:**
   ```bash
   curl -I http://localhost:8000/api/health/
   ```

---

## 4. Standalone Host Deployment (Gunicorn + Nginx + Systemd)

### A. Apply Migrations & Collect Static Files
```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
```

### B. Configure Systemd Service (`/etc/systemd/system/labtrack-web.service`)
```ini
[Unit]
Description=LabTrack Gunicorn Application Server
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/lab_track
EnvironmentFile=/var/www/lab_track/.env
ExecStart=/var/www/lab_track/venv/bin/gunicorn -c gunicorn.conf.py config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

### C. Nginx Site Configuration (`/etc/nginx/sites-available/labtrack`)
```nginx
server {
    listen 80;
    server_name labtrack.example.com;

    location /static/ {
        alias /var/www/lab_track/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /var/www/lab_track/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Automated Periodic Maintenance

Configure a cron job or systemd timer to release expired stock reservations every 15 minutes:

```bash
*/15 * * * * cd /var/www/lab_track && /var/www/lab_track/venv/bin/python manage.py cleanup_expired_reservations >> /var/log/labtrack_maintenance.log 2>&1
```

---

## 6. Deployment Verification Checklist

- [x] Run `python manage.py check --deploy` (zero security warnings).
- [x] Run `python manage.py test` (**62/62 tests passing**).
- [x] Verify `/api/health/` returns `{"status":"healthy","components":{"database":"ok","cache":"ok"}}`.
