# LabTrack Restructure Blueprint

## Goals
- Stabilize role-based workflows (student, faculty, admin) with one consistent data model.
- Remove naming drift (`student` vs `user`, `BorrowRequestItem` vs `BorrowItem`) through an explicit compatibility phase and then clean cutover.
- Split large views into layered modules so features can evolve safely.
- Make background jobs, notifications, and dashboard stats reliable.

## Current Pain Points
- Model/API drift across apps caused runtime breakages.
- Business rules are duplicated across `inventory` and `requests_app`.
- Views are monolithic and mix orchestration, permission, and data mutation logic.
- URL and template contracts changed faster than tests.
- Configuration currently mixes production defaults with local-only assumptions.

## Target Architecture
- `users`: identity, profile, groups, group membership, role gates.
- `inventory`: component catalog, reservation locking, stock mutation primitives.
- `requests_app`: borrow lifecycle state machine + audit + PDF export.
- `notifications`: feed + email dispatch policies.
- `core` (new package, incremental): shared role guards, service errors, and common query filters.

## Domain Rules (Canonical)
- Students can reserve/borrow only when their group is approved.
- Borrow lifecycle: `PENDING -> APPROVED -> ISSUED -> RETURNED`, with side paths `REJECTED`, `OVERDUE`, `PENALTY`.
- Stock lock happens at reservation/cart stage; `ISSUED` is a state transition only; stock restore happens on `RETURNED` and `REJECTED`.
- Every status transition writes an audit action.

## Phased Plan
1. Phase 1: Stability and Compatibility
- Keep compatibility aliases/properties while views/templates migrate.
- Fix broken queries, task names, and config leaks.
- Add regression tests for cross-app contracts.

2. Phase 2: Service Layer Extraction
- Introduce `requests_app/services/borrow_service.py` for lifecycle transitions.
- Introduce `inventory/services/reservation_service.py` for hold and release logic.
- Make views thin adapters only.

3. Phase 3: URL/View Refactor
- Split dashboards by role modules (`views/admin.py`, `views/faculty.py`, `views/student.py`).
- Normalize query params (status/filter/sort/page) across admin and faculty pages.

4. Phase 4: Data Model Cleanup
- Remove compatibility shims after all callsites move to canonical names.
- Add data migration checks and enforce stricter constraints.

5. Phase 5: UX and Ops
- Consolidate console pages.
- Add observability basics (structured logs for transitions, task outcomes).
- Finalize deployment-safe settings profile.

## Current Implementation Status (March 5, 2026)
- Phase 1 (in progress):
  - Compatibility aliases remain in place (`student`/`user`, `BorrowRequestItem`/`BorrowItem`).
  - Signup regressions fixed (faculty submit unblock, group-mode state retention).
  - Token-based mobile API introduced under `/api/` with role-scoped request access.
  - Regression coverage expanded for signup and API access contracts.
- Phase 2 (partial):
  - `requests_app/services/borrow_service.py` is active for core lifecycle transitions.
  - Reservation service extraction is still pending; inventory view layer still owns reservation orchestration.
- Phase 5 (partial):
  - Admin/faculty request queue UX refined (requester role clarity, reject remarks modal flow).
  - Admin dashboard converted to overview-only with dedicated request console routing.
  - Theme contrast and out-of-stock denoters improved across key inventory/request screens.
  - Navigation wording cleanup started; remaining copy harmonization still pending.
- Performance:
  - Major admin data-console query path refactored from per-component loops to bulk aggregates.
  - Maintenance queue keyword scanning moved to DB filtering.
- Ops hygiene backlog:
  - `.env` secrets are tracked in repo state and must be rotated + removed from VCS.
  - `__pycache__/` artifacts are tracked and should be purged from source control.
  - Reminder task currently marks reminders as sent even when email send fails; retry-safe behavior is pending.

## Testing Strategy
- Unit tests for lifecycle transitions and stock safety.
- Integration tests for role permissions and dashboard actions.
- Template/view smoke tests for all major routes.

## Acceptance Criteria
- No role can perform unauthorized transitions.
- Reservation and stock totals remain consistent across all flows.
- All dashboards load without field errors.
- Test suite and system checks pass cleanly.
