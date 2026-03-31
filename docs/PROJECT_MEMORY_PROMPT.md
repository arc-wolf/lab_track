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

- Students can borrow only after group approval.
- Borrow lifecycle:
  - `PENDING -> APPROVED -> ISSUED -> RETURNED`
  - side paths: `REJECTED`, `OVERDUE`, `PENALTY`.
- Reservation stage locks available stock.
- Rejection/return restores available stock.
- Action history must be persisted (`BorrowAction`).
- Rejection should capture human-readable remarks for auditability.

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

## Admin Console Intent

1. **Stock Console**: component CRUD, total vs available stock, limits.
2. **Request Console**: approve/reject/issue/return/penalty with full detail and audit.
3. **Component Policy Console**: fines, grace, maintenance keyword controls.
4. **Data Console**: analytics + risk patterns + movement visibility.
5. Plus maintenance queue, reports, admin profile.
6. **Admin Dashboard** is overview-only:
   - decision layer with priority inbox, not full action surface.
   - detailed actions happen in dedicated consoles.

## UI/UX Intent

- App has unified themed UI (glass/gradient style).
- Global feedback uses toast notifications.
- Branded custom error pages exist (`400/403/403_csrf/404/500`).
- Actions that mutate state must be POST + CSRF protected.
- Stock-unavailable components should be visually denoted, not implied.

## Engineering Guardrails

- Do not regress role permissions.
- Do not reintroduce GET-based state changes.
- Keep student shared-team behavior intact.
- Keep faculty self-assignment behavior for faculty-generated slips.
- Keep per-component fine fallback deterministic:
  - component override when set
  - otherwise global `LabPolicy` value
- Keep OTP flows secure and deterministic:
  - invalidate old active OTP when new OTP is issued for same purpose/email.
  - enforce expiry and one-time use.
- Update docs when behavior changes:
  - `docs/PROJECT_SYSTEM_OPERATIONS.md`

## Current Progress Snapshot

- Shared student/group cart and request visibility implemented.
- Group removal dual-confirm workflow implemented.
- Admin multi-console architecture implemented.
- OTP registration + OTP password reset implemented.
- Full-name login flow implemented.
- Toast message UX + custom error pages implemented.
- SMTP mail sending works when `.env` is correctly configured.
- Admin/faculty reject flow supports modal remarks.
- Request queues show requester role to avoid faculty-vs-student ambiguity.
- Profile update flow enforces stronger email/phone validation.
- Admin dashboard is overview-only; full request handling is in dedicated request console page.
- Admin API exposes `/api/admin/overview/` and `/api/admin/console-map/` for control-plane clients.
- Admin overview now uses count-driven priority logic:
  - prioritizes pending approvals, overdue/penalty workload, pending groups, low stock, and maintenance flags.
  - quick request glimpse surfaces urgent states first.
- Admin API also supports policy/fine administration:
  - `GET /api/admin/policy/`
  - `POST /api/admin/policy/update/`
  - `POST /api/admin/components/<id>/fines/`

## Known Operational Dependencies

- Email OTP requires valid SMTP env variables:
  - `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_USE_TLS`
  - `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_FROM_EMAIL`
- `.env` loading is expected in settings.
- Celery tasks power scheduled reminders/overdue updates.
- Rate limiting depends on Django cache; production should use a shared backend (Redis/memcached), not local-memory cache.

## Repo Hygiene Requirements

- Never commit secrets (`.env`, API keys, SMTP passwords) to source control.
- Never commit generated cache artifacts (`__pycache__/`, `.pyc`).
- Keep docs and behavior in sync whenever lifecycle/security semantics change.

## Response/Execution Expectation

- Prioritize correctness over quick hacks.
- Explain functional impact of each change.
- Run checks/tests after modifications.
- If uncertain about behavior, inspect existing flow before patching.
- Keep learning docs in sync for newcomers:
  - `docs/TUTORIAL.md` must reflect current project structure and implemented concepts.

---

When you make changes, append change notes in `docs/PROJECT_SYSTEM_OPERATIONS.md` Change Log.
