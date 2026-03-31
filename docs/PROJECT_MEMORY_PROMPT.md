# LabTrack Continuity Prompt (Project Memory)

Use this prompt whenever continuing development in this repository so behavior stays aligned with product intent and existing logic.

---

You are continuing work on **LabTrack** (IoT/Hardware lab management).  
Primary objective: preserve working flows, close loopholes, and evolve features without breaking role rules.

## Product Intention (Non-Negotiable)

1. **Lab-first governance**
   - Lab Admin has final operational control over stock, requests, returns, penalties, and analytics.
2. **Student work is team-oriented**
   - Students operate through group/team context, not purely individual isolated flow.
3. **Faculty gatekeeping**
   - Faculty approves groups and assigned borrow requests.
4. **Traceability**
   - Every major request transition must be auditable and understandable in UI.
5. **Operational clarity**
   - Errors and warnings must be explicit to users (no silent failures).

## Current Role Model

- `student`: shared team console, group-linked borrowing.
- `faculty`: group approval + assigned request approval.
- `admin` (lab incharge): full control consoles.

## Canonical Business Rules

- Students borrow group/team context only (after faculty approval).
- Faculty self-generates slips (auto-assigned).
- Borrow lifecycle: `PENDING → APPROVED → ISSUED → RETURNED | REJECTED | OVERDUE | PENALTY`.
- Cart reservation locks `available_stock` (`GroupCartLock`, `cart_locked_at`).
- `REJECTED`/`RETURNED` restores stock.
- Every transition audits `BorrowAction` (timestamped, role-aware, remarks).
- Rejection requires modal remarks.
- Penalty estimation: component fine fields → `LabPolicy` fallback (`per_day_fine`, `grace_days`, condition fines).
- Due default: 45 days from creation.
- Group member removal: dual-confirm (`GroupRemovalRequest`: PENDING→APPROVED→remove `GroupMember`).
- Stock limits: `student_limit`, `faculty_limit` per-component.
- Return logs condition/time (`return_condition`, `return_time`).

## Authentication & Identity Rules (Current)

- Signup role inferred by email domain:
  - `@am.students.amrita.edu` => student
  - `@am.amrita.edu` => faculty
- Full name is first-class identity for users:
  - Signup asks full name (internal username auto-generated).
  - Login accepts full name or email + password.
- Signup is OTP verified by email (6-digit, 10 min).
- Forgot-password is OTP based (6-digit, 10 min).
- Student faculty-incharge must be selected from registered faculty list only.

## Full Console & URL Map + Data Models (Recreation Blueprint)

**Key Models (for full recreation):**
- `users.Profile`: full_name, phone, group_id/name, faculty_incharge, role inference.
- `users.Group/GroupMember`: team structure, leader assignment.
- `users.GroupRemovalRequest`: dual-confirm removal.
- `users.EmailOTP`: purpose(SIGNUP/RESET), code, expiry, used.
- `users.APIToken`: per-user token.
- `inventory.Component`: total/available_stock, limits, per-fine overrides, category.
- `requests_app.BorrowRequest`: lifecycle status, group, cart_locked_at, due_date, return_condition/time.
- `requests_app.BorrowAction`: audit log (action, by_role, timestamp, remarks).
- `requests_app.LabPolicy`: global fines/grace/maintenance_keywords.
- `inventory.Reservation/CartItem`: temp locks.
- `notifications.Notification`: role-center.

**Consoles/URLs:**
**Student:**
- `/inventory/components/` : shared cart/reservation
- `/student/dashboard.html` : requests
- `/student/group_console/` : team mgmt
- `/student/profile_console/` : updates
- `/student/requests/` : history

**Faculty:**
- `/faculty/dashboard/` : assigned slips (filter/sort)
- `/faculty/groups/` : approvals
- `/faculty/profile_console/` : updates

**Admin:**
- `/admin/` : priority dashboard
- `/admin/requests/` : lifecycle actions
- `/admin/components/` : stock mgmt
- `/admin/policy/` : LabPolicy
- `/admin/analytics/` : KPIs/AI insights
- `/admin/maintenance/` : flagged queue
- `/admin/reports/` : exports
- `/admin/profile/` : profile

**Auth/API:** as before

## UI/UX Intent

- App has unified themed UI (glass/gradient style).
- Global feedback uses toast notifications.
- Branded custom error pages exist (`400/403/403_csrf/404/500`).
- Actions that mutate state must be POST + CSRF protected.
- Stock-unavailable components should be visually denoted, not implied.

## Engineering Guardrails (Recreation Rules) + Critical Risks

**Core Guardrails:**
- Role permissions strict: student **group-only** (no bypass → collapse), faculty assigned-only, admin full.
- No GET mutations (POST/CSRF only).
- Student **always** group-shared.
- Faculty auto-self-assign slips.
- Fine: component → LabPolicy fallback.
- OTP: single-use/10min/invalidate priors (no mismanagement holes).
- Profile: unique username, alpha name, IN-phone, email lock.
- API: APIToken/role-scope.
- Cache/DB as above.
- UX: **toast+error+logs always** (no silent failures).
- Tests mandatory.

**⚠️ Critical Risks to Avoid:**
❌ **1. Role Bypass**: Student individual borrow → system collapse.
❌ **2. Stock Desync**: Cart lock unreleased → inventory corruption.
❌ **3. Silent Failures**: Always toast/error/log.
❌ **4. OTP Reuse**: Invalidate old OTPs on new issue.

**Current Status**: All mitigated per code/docs (cart_service locks/releases, EmailOTP invalidate, toast UX, group gating).

## Current Progress Snapshot

- Shared student/group cart and request visibility implemented (`inventory/services/cart_service.py`, `GroupCartLock`).
- Group removal dual-confirm workflow implemented (`users.GroupRemovalRequest` model, leader/member consent).
- Admin multi-console architecture implemented (stock, requests, analytics, policy, maintenance, reports, profile).
- OTP registration + OTP password reset implemented (`users.EmailOTP` model, 6-digit/10min, resend, invalidate priors).
- Full-name login flow implemented (identity accepts full name/email/username).
- Toast message UX + custom branded error pages implemented (`400/403/403_csrf/404/500`).
- SMTP mail sending works when `.env` SMTP vars configured.
- Admin/faculty reject flow supports modal remarks (audit-logged in `BorrowAction`).
- Request queues show requester role (`Student`/`Faculty`) and identity explicitly.
- Profile update flow enforces: unique username, alphabet-only full name, India 10-digit phone, role-specific email locks post-verification.
- Admin dashboard overview-only (priority inbox: pending/overdue/penalty/groups/low-stock/maintenance); dedicated consoles for actions.
- Admin API control-plane: `/api/admin/overview/`, `/api/admin/console-map/`.
- Admin priority logic count-driven, urgent-first glimpse (`PENDING/OVERDUE/PENALTY`).
- Admin policy/fine APIs: `GET/POST /api/admin/policy/`, `POST /api/admin/components/<id>/fines/`.
- Per-component fine overrides (`fine_per_day`, `fine_damaged`, `fine_missing_parts`, `fine_not_working`) with `LabPolicy` fallback.
- Excel services (`inventory/services/excel_service.py`): admin import/export stock/requests.
- Minimal AI assistant endpoint (`core/services/ai_service.py`): read-only context ops.
- Token auth for mobile/API (`users.APIToken`, `/api/auth/token/`, `/api/me/`, role-scoped `/api/requests/`, `/api/components/`).
- Production hardening: cache backend config, DB `CONN_MAX_AGE`, gzip, DB indexes on hot paths.
- Notifications center role-wise (`notifications/` app).
- E2E tests with Playwright (`e2e/`, `tests/`).

## Known Operational Dependencies (Setup for Recreation)

**Env (.env):**
```
DJANGO_EMAIL_HOST=... DJANGO_EMAIL_PORT=587 DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_HOST_USER=... DJANGO_EMAIL_HOST_PASSWORD=... DJANGO_FROM_EMAIL=...
# Cache: CACHE_BACKEND=locmem:///?max_entries=1000 (dev) or django_redis:// (prod)
DATABASES__default__CONN_MAX_AGE=60  # reuse
```

- SMTP for OTP/notifications/Celery.
- Celery for `send_due_reminders`, overdue (success-check `reminder_sent`).
- Cache: prod Redis for rate-limits/sessions (locmem dev inconsistent multi-process).
- Indexes: migrations/00015_... covers hot queries.
- Admin seed: username `lab_admin`, pass `adminpass`.
- Migrations: Run `python manage.py migrate`.
- Dependencies: `pip install -r requirements.txt`, `npm install` (Playwright).
- Hygiene: `.gitignore` caches/secrets; `git rm --cached .env` if tracked.

## Repo Hygiene & Recreation Setup

- Secrets: `.env` never commit (use `.env.example`, rotate SMTP/prod creds).
- Caches: `__pycache__/`, `.pyc`, `node_modules/` ignored.
- TODO.md hygiene fixes complete; git commit pending.
- Structure: Django apps (`users/inventory/requests_app/notifications`), `api/`, `core/services/`, `staticfiles/templates/`, `e2e/tests/`.
- Sync: Update this prompt + `PROJECT_SYSTEM_OPERATIONS.md` on changes.
- Recreation flow: clone → env → migrate → createsuperuser/lab_admin → python manage.py runserver → test E2E.

## Response/Execution Expectation

- Prioritize correctness over quick hacks.
- Explain functional impact of each change.
- Run checks/tests after modifications.
- If uncertain about behavior, inspect existing flow before patching.
- Keep learning docs in sync for newcomers:
  - `docs/TUTORIAL.md` must reflect current project structure and implemented concepts.

---

When you make changes, append change notes in `docs/PROJECT_SYSTEM_OPERATIONS.md` Change Log.
