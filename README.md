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
3. Configure environment variables in `.env`.
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

## Documentation
- System operations (living doc): `docs/PROJECT_SYSTEM_OPERATIONS.md`
- Continuity prompt: `docs/PROJECT_MEMORY_PROMPT.md`
- Restructure roadmap: `docs/RESTRUCTURE_BLUEPRINT.md`
- Beginner tutorial (project-based): `docs/TUTORIAL.md`
- API Postman testing guide: `docs/API_POSTMAN_TESTING.md`
