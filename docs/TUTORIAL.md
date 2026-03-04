# LabTrack Django Tutorial (Zero to Practical)

Last updated: March 4, 2026

## 1) Who This Is For
This tutorial is for you if:
- You are new to programming.
- You are new to Python.
- You are new to Django.
- You want to understand this project by learning directly from real code.

You do not need prior coding knowledge.

## 2) What This Project Is
LabTrack is a web app for managing an IoT/Hardware lab.

It supports 3 main user roles:
- `student`: reserve components and create borrow requests (team/group flow).
- `faculty`: approve student groups and assigned borrow requests.
- `admin`: full lab control (inventory, request lifecycle, analytics, policies).

Think of this app like a "smart lab office":
- Students ask to borrow components.
- Faculty approves academic-side requests.
- Admin controls stock and return process.

## 3) First Big Idea: How a Web App Works
When you open a page in a browser:
1. Browser sends a request to server.
2. Server reads the request, runs code, talks to database.
3. Server sends back a response (HTML/JSON).
4. Browser shows result.

In Django:
- `urls.py` decides which function handles the request.
- `views.py` contains handling logic.
- `models.py` defines database tables/data.
- `templates/*.html` define page structure.

## 4) Very Basic Python You Need
Python is a human-readable programming language.

Examples:
```python
name = "Asha"
if name == "Asha":
    print("Hello")
```

Key things you will see often:
- Variables (`name = ...`)
- Functions (`def my_function(): ...`)
- Conditions (`if`, `elif`, `else`)
- Lists and loops (`for item in list`)

Do not worry about memorizing everything first. Learn by reading project code with this map.

## 5) Project Structure (This Repository)
Top-level important folders:
- `config/`: project settings and global URL map.
- `users/`: login/signup, OTP, profiles, roles, groups.
- `inventory/`: components, cart/reservations, stock.
- `requests_app/`: request lifecycle and admin/faculty consoles.
- `notifications/`: notification center page.
- `api/`: token-based JSON endpoints for external/mobile use.
- `templates/`: HTML pages.
- `docs/`: project documentation (including this tutorial).

## 6) How to Run the Project Locally
From project root:
1. Install dependencies:
   - `pip install -r requirements.txt`
2. Apply DB migrations:
   - `python manage.py migrate`
3. Start server:
   - `python manage.py runserver`
4. Open browser:
   - `http://127.0.0.1:8000/`

To run tests:
- `python manage.py test`

## 7) Django Concepts Used in This Project

### 7.1 Models (Database Tables)
Models are Python classes that represent DB tables.

Examples:
- `users.Profile`
- `inventory.Component`
- `inventory.Reservation`
- `requests_app.BorrowRequest`
- `requests_app.BorrowAction`

What they do:
- Store app data (users, stock, requests, status history).
- Define relationships (example: one request has many items).

### 7.2 Migrations
Migration files are versioned database changes.

If model changes, you do:
1. `python manage.py makemigrations`
2. `python manage.py migrate`

This keeps database schema aligned with code.

### 7.3 URLs and Views
`urls.py` routes a URL path to a view function/class.

Example flow:
- URL `/inventory/components/`
- mapped in `inventory/urls.py`
- handled by `inventory/views.py -> student_dashboard`
- renders template `templates/student/dashboard.html`

### 7.4 Templates
Templates are HTML pages with Django tags.

Examples:
- `{% if ... %}` conditions
- `{{ variable }}` print data
- `{% url 'route_name' %}` generate links

### 7.5 Forms
Forms validate user input.

Examples:
- Signup form validates organization email.
- Phone validation checks format.
- Login form accepts full name or email as identity.

### 7.6 Authentication and Sessions
Web login uses Django sessions:
- User logs in once.
- Browser stores session cookie.
- Protected pages use `@login_required`.

After logout:
- Session is invalid.
- This project also adds no-store cache headers for authenticated pages to reduce stale back-page view.

### 7.7 Authorization (Role-based Access)
Not every logged-in user can do everything.

Role checks are done in view logic:
- Student-only pages
- Faculty-only approvals
- Admin-only operations

### 7.8 Middleware
Middleware runs on every request/response.

This project uses custom middleware:
- `users.middleware.NoStoreForAuthenticatedPagesMiddleware`
- Adds cache-control headers for private authenticated HTML pages.

### 7.9 Caching
Cache stores frequently used results temporarily.

In this project:
- Used for rate-limit counters.
- Used for small hot data (like API components list, category list).
- Configurable backend: local memory or Redis.

### 7.10 Background Jobs (Celery)
Some tasks run on schedule, not in user request cycle:
- Clear expired reservations.
- Send due reminders.
- Mark overdue requests.

This keeps UI requests faster and automation reliable.

### 7.11 API (JSON Endpoints)
Separate from web pages:
- `/api/auth/token/` issues API token.
- `/api/me/`, `/api/components/`, `/api/requests/` return JSON.

Use case:
- Mobile app or external client can use token auth.

### 7.12 Tests
Tests verify behavior automatically.

Current tests cover:
- Signup/OTP behavior
- Dashboard redirects
- Slip lifecycle actions
- API token and access rules
- Auth identity/cache behavior

## 8) Core Business Flow in LabTrack

### 8.1 Student Borrow Flow
1. Student logs in.
2. Student group must be approved.
3. Student adds components to cart (creates reservation lock).
4. Student generates borrow slip.
5. Request becomes `PENDING`.

### 8.2 Approval and Issue Flow
1. Faculty/Admin approves -> `APPROVED`.
2. Admin marks collection -> `ISSUED`.
3. Admin marks returned -> `RETURNED`.

Alternative statuses:
- `REJECTED`
- `OVERDUE`
- `PENALTY`

### 8.3 Why `BorrowAction` Exists
Each important status change creates a log row.

That gives audit/history:
- Who changed what
- When it happened
- Any notes

## 9) Important Safety/Quality Ideas in This Project

### 9.1 Stock Safety
Stock updates use DB transactions and row locks.

Purpose:
- Prevent two users from over-reserving at the same moment.
- Keep `available_stock` consistent.

### 9.2 OTP Security
OTP records:
- expire after time limit
- are one-time use
- old active OTPs get invalidated when new OTP issued

### 9.3 Rate Limiting
Used on login/token/OTP actions to reduce abuse.

## 10) Beginner Mental Model for Reading Any New File
When you open a file, ask:
1. Is this data (`models`)?
2. Is this routing (`urls`)?
3. Is this action logic (`views`/`services`)?
4. Is this user interface (`templates`)?
5. Is this configuration (`settings`)?
6. Is this automated check (`tests`)?

This simple classification removes confusion quickly.

## 11) Your First Learning Path (Step-by-Step)
Follow this order:
1. `config/urls.py` (global map of routes).
2. `users/views.py` (auth + role redirects).
3. `inventory/views.py` (student cart and reservations).
4. `requests_app/views.py` and `requests_app/services/borrow_service.py` (lifecycle).
5. `users/models.py`, `inventory/models.py`, `requests_app/models.py` (data model).
6. `templates/student/dashboard.html` and `templates/admin/dashboard.html` (UI outcomes).
7. `users/tests/`, `requests_app/tests/`, `api/tests.py` (how behavior is validated).

## 12) Glossary (Simple)
- `Model`: DB table definition in Python.
- `View`: Python function/class that handles request.
- `Template`: HTML page.
- `URL route`: path to view mapping.
- `Migration`: versioned DB schema update.
- `Session`: server-tracked logged-in state for browser.
- `Cache`: temporary memory storage to avoid repeated expensive work.
- `Middleware`: cross-cutting request/response hook.
- `API`: machine-readable endpoint (usually JSON).
- `Celery task`: background job.

## 13) Common Beginner Mistakes and How to Avoid
- Mistake: editing models without migration.
  - Fix: always run `makemigrations` and `migrate`.
- Mistake: changing URL without updating template link.
  - Fix: use named URLs and check route names.
- Mistake: putting all logic in templates.
  - Fix: keep business logic in views/services/models.
- Mistake: skipping tests.
  - Fix: run `python manage.py test` before/after major changes.

## 14) Practice Exercises
1. Add one small read-only page showing total components and total requests.
2. Add one new field to `Profile` (example: department), migrate DB, and show in profile page.
3. Add one test that checks unauthorized user cannot access an admin route.
4. Add one API endpoint that returns app health info (version, current time).

These will teach routing, models, templates, permissions, and tests together.

## 15) Final Advice
You do not need to learn all of Django first.
Learn in loops:
1. Read one flow.
2. Run app.
3. Change one small thing.
4. Run tests.
5. Repeat.

That is how real project learning becomes fast and practical.
