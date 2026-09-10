# LabTrack - Production Hardware & Inventory Management System

**LabTrack** is an enterprise-ready hardware component inventory, team reservation, and borrow request management system built with Django 6.0 and Python 3.12.

---

## 🌟 System Architecture & Domain Services

LabTrack follows a clean, decoupled service-layer architecture separating business logic from HTTP view controllers:

```
lab_track/
├── config/             # Settings, WSGI/ASGI, global URLs, RequestID & Performance Middleware
├── api/                # REST API endpoints, serializers, token authentication & health diagnostics
├── inventory/          # Component stock, cart reservations (15-min TTL), reservation service layer
├── requests_app/       # Borrow request slips, approval console, PDF generation, borrow service layer
├── notifications/      # Role-filtered notification center & alert service layer
├── users/              # Profiles, OTP authentication, team groups, group management services
└── docs/               # Technical manuals, API guides, deployment documentation
```

### Key Domain Services
- **`notifications/services/notification_service.py`**: Encapsulates role-based notification compilation (`Admin`, `Faculty`, `Student`).
- **`users/services/group_service.py`**: Handles student group creation, leader auto-promotion, and dual-consent removal workflows.
- **`users/services/profile_service.py`**: Provides identity validation, phone formatting, OTP generation, and rate limiting.
- **`inventory/services/reservation_service.py`**: Manages cart hardware reservations with automatic 15-minute stock holds.
- **`requests_app/services/borrow_service.py`**: Controls borrow request approvals, hardware collection, returns, and fine estimates.

---

## 🔒 Security & Middleware

- **Request Tracing & Performance Monitoring:** `config.middleware.RequestIDAndPerformanceMiddleware` injects `X-Request-ID` into all HTTP responses and flags slow requests (>500ms).
- **Role-Based Access Control (RBAC):** Strict isolation between `Student`, `Faculty`, and `Admin` users.
- **API Token Security:** Header-authenticated REST endpoints under `/api/admin/*` requiring valid `APIToken` authorization.
- **OTP Authentication:** Signup and password resets gated by 6-digit email OTPs with rate-limiting protection.

---

## 🚀 Local Development Setup

1. **Activate Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Setup:**
   Copy `.env.example` to `.env` and fill in required secrets.

4. **Database Migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Run Development Server:**
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

---

## 🛠️ Production Maintenance Command

Release expired component reservations and purge stale OTP records:
```bash
DJANGO_SECRET_KEY="<production-secret-key>" python manage.py cleanup_expired_reservations
```

---

## 🧪 Testing & Verification

Execute the complete 62-test automated suite (including 100% endpoint coverage and end-to-end UI user journey tests):

```bash
python manage.py test
```

Run deployment security check:
```bash
DJANGO_ENV=production DJANGO_SECRET_KEY="<production-secret-key>" python manage.py check --deploy
```

---

## 🐳 Production Deployment (Docker)

1. **Build and Start Container Stack:**
   ```bash
   docker compose up -d --build
   ```

2. **Run Migrations in Container:**
   ```bash
   docker compose exec web python manage.py migrate
   ```

3. **Verify System Health:**
   ```bash
   curl http://localhost:8000/api/health/
   ```

---

## 📚 Documentation Resources
- [Production Deployment Guide](file:///root/lab_track/docs/PRODUCTION_DEPLOYMENT.md)
- [API Reference & Testing Guide](file:///root/lab_track/docs/API_POSTMAN_TESTING.md)
