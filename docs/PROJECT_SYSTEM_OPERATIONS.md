# LabTrack Project System Operations (Living Document)

Last updated: March 3, 2026
Owner: Engineering team

## 1) Purpose
This document is the single source of truth for:
- What the project does.
- How each role operates in the system.
- What each console/page is responsible for.
- What was transformed from previous behavior.
- What must be updated whenever code changes.

This file must be updated on every functional code change.

## 2) Role Model
- `student`: Uses shared team console, group-based borrow flow.
- `faculty`: Approves group requests and student borrow requests assigned to them.
- `admin` (Lab Admin): Full control of stock, requests, analytics, policies, and admin profile.

## 3) High-Level Module Map
- `users`: profiles, group model, group membership, signup flow, group approval, role dashboards.
- `inventory`: component stock, reservation/cart locking, admin stock CRUD.
- `requests_app`: borrow request lifecycle, action audit trail, admin/faculty dashboards, analytics.
- `notifications`: role-wise alerts center.

## 4) Functionalities and Operations

### 4.1 Authentication, Signup, OTP, and Password Reset
- Signup derives role by email domain:
  - `@am.students.amrita.edu` -> student
  - `@am.amrita.edu` -> faculty
- Registration is now **OTP-gated**:
  - Valid form submit sends 6-digit OTP to registering email.
  - Account is created only after OTP verification.
  - OTP validity: 10 minutes.
  - Resend OTP supported.
- Login is **Identity + Password**:
  - Login form accepts full name or registered email.
  - Backend resolves identity to internal username.
  - If multiple accounts share the same full name, login is blocked with explicit message.
- Forgot-password flow is **OTP-based** (not link-only):
  - User enters registered email.
  - OTP is sent.
  - OTP + new password complete reset.
- Student signup supports:
  - `create group`: generates unique Group ID.
  - `join group`: case-insensitive group code validation and normalization.
- Student `Faculty Incharge` is restricted to select-only from registered faculty list.
- Phone numbers are validated to allow only 10-15 digits with optional leading `+`.
- Full name is mandatory in signup for both students and faculty.
- Admin seed account:
  - Username: `lab_admin`
  - Password: `adminpass`

### 4.2 Student Shared Console (Group-first behavior)
- Student dashboard is shared by team context, not personal-only.
- Group ID is visible and copyable for teammate onboarding.
- Reservations/cart are shared by group members:
  - Team sees all active reservations for all members in group.
  - Add-to-cart merges same component reservation at team scope.
  - Removal is allowed from shared cart.
- Borrow requests list is group-scoped for students (team can track all group slips).
- Group approval is required before borrowing operations proceed.
- During slip generation:
  - Students must select faculty incharge.
  - Faculty users do not select faculty (auto-assigned to self).

### 4.3 Student Group Console
- Dedicated team page for:
  - Viewing all group members.
  - Viewing own role (Leader/Member).
  - Managing member-removal requests with dual confirmation.
- Team leader assignment:
  - Creator is set as `LEADER` during group creation signup path.
  - If no leader exists in old data, earliest member is auto-promoted when opening group console.

### 4.4 Member Removal Protocol (Student Team)
- Removal requires both parties:
  - Member confirmation.
  - Leader confirmation.
- Either side can initiate:
  - Leader can start removal for member.
  - Member can request self-removal.
- Request states:
  - `PENDING` -> waiting other side confirmation.
  - `APPROVED` -> member removed from group.
  - `CANCELLED` -> request closed manually.
- On approval:
  - Member’s `GroupMember` row deleted.
  - Member profile group linkage cleared (`group_id`, `group_name`, `faculty_incharge`).

### 4.5 Faculty Operations
- Faculty dashboard:
  - Filters, search, sort, pagination.
  - Sees assigned requests and request details.
  - Approves pending slips assigned to them.
- Faculty groups page:
  - Sees assigned groups.
  - Approves/rejects pending groups.
- Faculty profile console:
  - Update full name, phone, email, password.

### 4.6 Admin Operations (Lab Admin)
Lab Admin has four operational consoles plus profile:

1. Stock Console (`admin/components`)
- Component CRUD with:
  - `total_stock` (real total count)
  - `available_stock` (visible/borrowable count)
  - `student_limit` and `faculty_limit` enforcement values
- Search + category filter + stock-state filter (`low`, `out`).

2. Request Console (`requests/admin`)
- Unified queue for all requests.
- Admin actions:
  - Approve
  - Reject/Terminate
  - Mark Collected (`ISSUED`) with mandatory collector name entry
  - Mark Penalty
  - Mark Returned + condition logging
- Detail panel includes:
  - Group info
  - Cart lock time (`cart_locked_at`)
  - Request creation time
  - Due date
  - Return condition/time
  - Action history
- UI shows toast notifications for errors/warnings/success events instead of basic inline alerts.

3. Component Data Console (`requests/admin/data-console`)
- Analytics dashboard with:
  - KPI cards (pending/issued/returned/penalty/overdue/etc.)
  - Chart visualization (collected vs returned vs penalized)
  - Component movement matrix
  - Return quality log (including damaged/critical conditions)
  - AI-style recommendations generated from operational patterns

4. Component Policy Console (`requests/admin/component-console`)
- Editable policy parameters:
  - `per_day_fine`
  - `grace_days`
  - `overdue_penalty_trigger_days`
  - `damaged_fine`
  - `missing_parts_fine`
  - `not_working_fine`
  - `maintenance_keywords`
  - `notes`

Additional admin consoles:
- Maintenance Queue (`requests/admin/maintenance-queue`)
- Reports Console (`requests/admin/reports-console`)
- Admin Profile Console (`users/admin/profile-console`)

### 4.7 Borrow Lifecycle and Stock Behavior
Request statuses:
- `PENDING`, `APPROVED`, `ISSUED`, `RETURNED`, `PENALTY`, `OVERDUE`, `REJECTED`

Operational behavior:
- Reservation stage reduces `available_stock`.
- `APPROVED` confirms request state.
- `ISSUED` marks collection event.
- `RETURNED` restores stock and logs return condition.
- `REJECTED` restores stock.
- All status transitions are audit-logged in `BorrowAction`.

Due policy:
- Default due date is now 45 days from request creation when due is not explicitly set.

### 4.8 Notifications
- Role-wise notification center:
  - Admin: low stock, pending approvals, due today.
  - Faculty: group approval requests, pending slip approvals, due today.
  - Student: own request notifications.
- Notification template was aligned to `slip.user` (not legacy `slip.student`).

### 4.9 Error Handling UX
- Custom themed error pages added:
  - `400`, `403`, `403_csrf`, `404`, `500`
- These are active when `DEBUG=False`.
- Runtime action feedback uses toast messages (top-right) with severity color + auto-hide.
- Authenticated HTML responses use no-store/no-cache headers to reduce stale private pages shown via browser Back after logout.

### 4.10 Mobile/External API Access
- Token-based JSON API is available under `/api/` for mobile clients (e.g., Flutter).
- Authentication:
  - `POST /api/auth/token/` with JSON body `{ "identity": "...", "password": "..." }`
  - `identity` supports username, email, or full name.
  - Returns `{ "token": "...", "user": {...} }`
- Logout/rotation:
  - `POST /api/auth/logout/` with header `Authorization: Token <token>`
- Profile:
  - `GET /api/me/`
- Components:
  - `GET /api/components/`
- Borrow requests:
  - `GET /api/requests/`
  - Access is role-scoped:
    - admin: all recent requests
    - faculty: assigned requests
    - student: group-scoped (or own requests if no group)
- API serialization layer:
  - Response payloads are centralized in `api/serializers.py`.
  - `api/views.py` now delegates JSON shape construction to serializer helpers.

### 4.11 Recent Stability/Performance Fixes
- Signup UX fix:
  - Faculty signup submit no longer stalls due to hidden student-only required fields.
  - Student `group_mode` (create/join) selection is preserved after validation errors.
- Admin analytics optimization:
  - `requests/admin/data-console` was refactored from per-component nested query loops to bulk aggregate queries.
  - Maintenance queue keyword detection now filters in DB instead of scanning all returned rows in Python.
- Production efficiency hardening:
  - Added DB connection reuse setting under `DATABASES['default']['CONN_MAX_AGE']` (env-driven).
  - Added configurable cache backend (`locmem` or Redis) and cached DB sessions for lower auth/session DB load.
  - Added gzip middleware for compressed responses.
  - Added targeted DB indexes on high-traffic query paths (`BorrowRequest`, `BorrowAction`, `BorrowItem`, `Profile`, `Group`, `GroupMember`, `GroupRemovalRequest`).
  - Reduced repeated DB lookups in faculty resolution logic and cached component category list for dashboard rendering.

## 5) Data Model Additions/Alterations
- `requests_app.BorrowRequest`
  - Added `cart_locked_at`.
  - Default due computation changed to +45 days.
- `requests_app.LabPolicy`
  - New singleton-style policy model for penalties/maintenance triggers.
- `users.GroupRemovalRequest`
  - New dual-consent member removal workflow model.
- `users.EmailOTP`
  - Stores OTP by email and purpose (`SIGNUP`, `PASSWORD_RESET`), expiry, and used state.
- `users.APIToken`
  - One-to-one token per user for mobile/external API authentication.

## 6) URL/Console Map (Operational)
- Student:
  - `/inventory/components/` -> shared student console
  - `/users/student/group-console/` -> team member + removal workflow
  - `/users/student/profile-console/` -> student profile
- Faculty:
  - `/requests/faculty/` -> faculty request console
  - `/users/groups/` -> faculty group approvals
  - `/users/faculty/profile-console/` -> faculty profile
- Admin:
  - `/requests/admin/` -> request console
  - `/inventory/admin/components/` -> stock console
  - `/requests/admin/component-console/` -> policy console
  - `/requests/admin/data-console/` -> analytics console
  - `/requests/admin/maintenance-queue/` -> maintenance queue
  - `/requests/admin/reports-console/` -> reports
  - `/users/admin/profile-console/` -> admin profile
- Auth/Recovery:
  - `/accounts/login/` -> identity login view (full name or email)
  - `/accounts/signup/` -> OTP-enabled signup
  - `/accounts/signup/resend-otp/` -> resend signup OTP
  - `/accounts/password-reset/` and `/accounts/password_reset/` -> OTP reset request
  - `/accounts/password-reset/verify/` -> OTP + new password confirm
  - `/accounts/password-reset/resend-otp/` -> resend reset OTP

## 7) Transformation Script (Plain English)
This is the functional transformation from old behavior to current behavior:

1. Unified data-field drift:
- Moved to canonical `BorrowRequest.user` while preserving compatibility for legacy references.

2. Enforced group approval gating:
- Students cannot borrow until faculty/admin approves their group.

3. Converted student personal flow to team-shared flow:
- Team reservations and team request visibility are now group-scoped.

4. Added team governance:
- Introduced leader/member semantics and dual-consent member removal process.

5. Elevated admin to full lab operations:
- Built complete console ecosystem: stock, request lifecycle, policy, analytics, maintenance, reports.

6. Added policy and analytics depth:
- Penalty and maintenance parameters are editable.
- Data console includes charts, movement analytics, and AI-style insights.

7. Added role profile consoles:
- Student, faculty, and admin can update personal details (and password).

8. Stabilized notifications and dashboard rendering:
- Fixed field mismatches and linked role-appropriate actions.

## 8) Mandatory Update Protocol (Must follow for every code change)
Whenever any functionality changes:

1. Update this file (`docs/PROJECT_SYSTEM_OPERATIONS.md`):
- Update section `4) Functionalities and Operations`.
- Update section `5) Data Model Additions/Alterations` if model changed.
- Update section `6) URL/Console Map` if route changed.
- Append one line under `9) Change Log`.

2. If behavior changes, update tests in same commit.

3. If DB schema changes, include migration and note it in change log.

## 9) Known Risks / Cleanup Backlog
- Secrets hygiene:
  - `.env` is currently tracked in git and contains real SMTP credentials in this repository state.
  - Action required: rotate credentials, remove secrets from VCS history, and keep only `.env.example` in repo.
- Repository hygiene:
  - `__pycache__/` and `.pyc` artifacts are currently tracked.
  - Action required: remove tracked caches and keep only source-controlled files.
- Background task reliability:
  - Reminder task marks `reminder_sent=True` even if mail delivery fails; retries are skipped after transient failures.
  - Action required: mark as sent only on successful send (or add explicit retry/failure state).
- Rate-limit consistency:
  - Auth/API rate limits rely on Django cache; without shared cache backend, multi-worker deployments can get inconsistent enforcement.
  - Action required: configure shared cache (e.g., Redis) for production.

## 10) Change Log (append-only, newest first)
- 2026-03-04: Added `docs/API_POSTMAN_TESTING.md` and inline API endpoint comments in `api/urls.py` for faster Postman-based validation.
- 2026-03-04: Added beginner-friendly `docs/TUTORIAL.md` and linked it from project docs for onboarding from zero programming background.
- 2026-03-04: Added production-efficiency hardening (cache backend config, DB connection reuse, gzip middleware, query/index optimization, and hot-path caching).
- 2026-03-04: Added no-store cache headers for authenticated pages, identity login (full-name or email), and stronger phone validation.
- 2026-03-04: Synced docs with current code behavior and added explicit known-risk backlog (secrets, cache artifacts, reminder retry semantics, cache-backed rate limiting).
- 2026-03-03: Optimized admin analytics and maintenance queue query paths to reduce N+1/per-component query load.
- 2026-03-03: Fixed signup form behavior for faculty submissions and preserved student group mode selection on validation errors.
- 2026-03-03: Added API serializer module (`api/serializers.py`) and routed API responses through centralized serializers.
- 2026-03-03: Added token-based `/api/` access for external/mobile clients with role-scoped request listing and component/profile endpoints.
- 2026-03-01: Implemented OTP verification for signup and forgot-password, added `EmailOTP` model, and OTP resend endpoints/pages.
- 2026-03-01: Switched login to full-name based authentication and enforced full-name-first registration.
- 2026-03-01: Enforced student faculty-incharge selection from registered faculty list only.
- 2026-03-01: Faculty slip generation auto-assigns faculty (no dropdown needed for faculty users).
- 2026-03-01: Added themed error pages (`400/403/403_csrf/404/500`) and toast-based global messaging.
- 2026-03-01: Admin `Mark Collected` now requires collector name and logs it in issued action history.
- 2026-03-01: Added student shared console behavior, group removal dual-consent workflow, admin policy/maintenance/report consoles, admin/faculty/student profile consoles, 45-day due policy, and analytics upgrades.
