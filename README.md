# LabTrack
IoT/Hardware lab management system for student teams, faculty approvals, and lab admin operations.

## Core Apps
- `users`: profiles, role model, groups, signup/login/OTP flows.
- `inventory`: component catalog, stock, reservation/cart locking.
- `requests_app`: borrow lifecycle, audits, dashboards, policies, reports, PDF slips.
- `notifications`: role-wise notification center.
- `api`: token-based JSON API for external/mobile clients.

## Auth Notes
- Web login accepts full name or registered email as identity.
- Signup and password reset are OTP-gated email flows.

## Local Run
1. Create and activate virtualenv.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure environment variables in `.env` (copy from `.env.example`).
4. Apply migrations:
   - `python manage.py migrate`
5. Start development server:
   - `python manage.py runserver`

## Background Jobs
- Celery worker:
  - `celery -A config worker -l info`
- Celery beat scheduler:
  - `celery -A config beat -l info`

## Tests
- Run all tests:
  - `python manage.py test`

## Production Readiness Checklist
1. Create `.env` from `.env.example` and set real values.
2. Set `DJANGO_DEBUG=False`.
3. Set a strong `DJANGO_SECRET_KEY`.
4. Set real `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
5. Enable HTTPS at reverse proxy and keep:
   - `DJANGO_SECURE_SSL_REDIRECT=True`
   - `DJANGO_SESSION_COOKIE_SECURE=True`
   - `DJANGO_CSRF_COOKIE_SECURE=True`
6. Use Redis cache/session backend in production:
   - `DJANGO_CACHE_BACKEND=redis`
   - `DJANGO_CACHE_URL=redis://...`
7. Run:
   - `python manage.py check --deploy`
   - `python manage.py test`

## Push To Your Git
1. Verify remote:
   - `git remote -v`
2. Add and commit:
   - `git add -A`
   - `git commit -m "production hardening + cleanup"`
3. Push:
   - `git push origin master`
4. If Git asks for auth, use your GitHub PAT/token in the prompt.

## Documentation
- System operations (living doc): `docs/PROJECT_SYSTEM_OPERATIONS.md`
- Continuity prompt: `docs/PROJECT_MEMORY_PROMPT.md`
- Restructure roadmap: `docs/RESTRUCTURE_BLUEPRINT.md`
- Beginner tutorial (project-based): `docs/TUTORIAL.md`
- API Postman testing guide: `docs/API_POSTMAN_TESTING.md`
