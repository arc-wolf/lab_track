# LabTrack Manual Test Plan

## Scope & Environments
- Target: Web UI (student, faculty, admin), token API, background jobs (Celery), PDF generation.
- Environments: local dev (`DEBUG=True`) with SQLite, staging/prod with configured email/Redis/Celery. Use seeded fixture or the provided seed script for users and components.
- Supported browsers: Chrome (latest), Firefox (latest), mobile Safari (latest).

## Accounts & Seed Data (reference)
- Lab admins: `labadmin1` / `LabAdmin@123`, `labadmin2` / `LabAdmin@123`
- Faculty: `faculty1`–`faculty5` / `Faculty@123`
- Students: `student01`–`student10` / `Student@123`
- Groups: `GRP100` (approved, faculty1), `GRP200` (pending, faculty2)
- Components: 50 seeded items across categories.

## Test Matrix (manual)

### 1. Authentication & Profile
- Signup (student email domain) requires OTP; hides group fields for faculty emails.
- Student signup dropdowns: program, branch, batch required; group mode create/join validations; faculty-in-charge required only on create.
- Login accepts full name or email; wrong password shows error; lockout not implemented (verify message only).
- Logout clears session; navigating back does not expose cached authed pages (cache-control headers).
- Profile console: update name/phone; verify phone validation; email locked for students; admin email change blocked.

### 2. Group Management
- Student group console lists members with name/email/program/batch; leader badge visible; removal workflow:
  - Member self-removal needs member + leader confirm.
  - Leader-initiated removal requires member confirm.
  - After removal, profile group_id cleared.
- Faculty console: approve/reject group; group status propagates to student dashboard borrow access.
- Pre-assigned faculty: cart shows fixed faculty; slip generation succeeds without manual selection.

### 3. Inventory & Cart
- Student dashboard:
  - Category filter + search functional; search button aligned.
  - Max allowed / remaining counters update; when remaining=0, add-to-cart disabled and warning shown.
  - Reservation expiry (15 min) releases stock (simulate by adjusting expires_at and refreshing).
- Add to cart:
  - Quantity cannot exceed available stock or component limit; shows error.
  - Group members share reservations; counts aggregate across group.
- Remove item restores stock.
- Faculty user can add without student limits; faculty limit respected if set.

### 4. Borrow Slip Generation
- For approved group with faculty set: generate slip without selecting faculty; PDF downloads.
- For pending group: slip blocked with message.
- Project title required; missing title blocks submission.
- Upon slip creation: reservations consumed; BorrowRequest status = PENDING; due date default 45 days; BorrowAction CREATED logged.

### 5. Requests Lifecycle (Admin/Faculty)
- Admin request console filters by status; approve/reject/issue/return/penalty transitions valid.
- Faculty dashboard: sees assigned requests; can approve/reject/mark issued/returned.
- Overdue job: set due_date to past, run `update_overdue_requests` task, status becomes OVERDUE.
- Penalty flow: mark penalty allowed only from ISSUED/OVERDUE.

### 6. Notifications Center
- Admin: low-stock list (< =2), pending requests, due today.
- Faculty: pending group approvals, pending slips, due today for their requests.
- Student: sees own/group requests list.

### 7. Due-Date Reminders
- Set due_date to today+5 and reminder_sent=False; run `send_due_reminders`; emails queued to student and faculty (group faculty if present); reminder_sent flips True.

### 8. PDF Slip Format
- Header excludes request id/status; dates format dd/mm/yyyy.
- Table headers: Sl No, Equipment/Component, Qty, Request Date, Collected Date, Return By, Remarks.
- “Return By” equals due date; “Collected Date” blank; “Request Date” matches created_at.
- File name format `borrow_request_<id>.pdf`.

### 9. UI/Theme/Accessibility
- Dark mode: accordion texts readable (groups page and all accordions); live clock updates each second with fallback.
- Buttons/links contrast in both themes; keyboard focus visible on accordions and form inputs.
- Responsive: student dashboard cards, filters, cart tables readable on 360px wide screen; navbar wraps correctly.

### 10. Data Integrity & Limits
- Component adjust_available never allows negative stock (concurrent add/remove simulated via transactions).
- Reservation uniqueness per user+component when active; duplicate add merges quantity respecting limits.
- BorrowRequest due date auto-set on save if missing.

### 11. APIs (token-based)
- Auth token creation via users.APIToken model (not exposed in UI); existing endpoints return JSON and enforce role (spot-check inventory list, requests list).
- Unauthorized requests return 401/403 as appropriate.

### 12. Background Jobs & Schedules
- Celery worker runs tasks without errors; beat schedule triggers reminder and overdue tasks.
- Tasks are idempotent (re-running reminder on same day does not resend because reminder_sent=True).

### 13. Security & Permissions
- Non-student blocked from student dashboard/cart.
- Students cannot download others’ slips; faculty/admin can download relevant slips.
- Admin-only consoles protected by role check.
- Form CSRF tokens present on all POST forms (spot-check cart remove, slip generate, group actions).

### 14. Error Handling
- Empty cart generate slip shows message.
- Invalid quantity or expired reservation shows error toast.
- Selecting faculty not matching approved group in-charge is blocked with message.

## Regression Checklist (quick run)
1. Student signup (valid + invalid domain).
2. Student add-to-cart, max limit hit, removal.
3. Slip creation with pre-assigned faculty.
4. PDF download, check headers/columns/date formats.
5. Admin approve → issue → return flow.
6. Overdue task flips status.
7. Reminder task marks reminder_sent.
8. Dark-mode accordion readability on `/users/groups/`.

## Execution Notes
- Prefer running `./venv/bin/python manage.py test` for automated coverage; manual cases above cover cross-role UX and PDF layout.
- For time-dependent tasks, use Django shell to manipulate `due_date`/`expires_at`.
- Capture screenshots of key UI regressions and PDFs when reporting.
