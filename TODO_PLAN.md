# LabTrack Bug/Risk Fix Plan (Approved)
Current: /root/Desktop/lab_track

## Steps (Sequential)

### 1. [x] Update docs/PROJECT_SYSTEM_OPERATIONS.md
- Added changelog entry: '2026-03-25: Updated docs/PROJECT_SYSTEM_OPERATIONS.md changelog for memory prompt hygiene update.'

### 2. [x] Fix requests_app/tasks.py reminder success-check
- Moved `req.reminder_sent=True/save()` inside `try:` after `send_mail()` success (fail → log only, no mark).

### 3. [x] Git hygiene: .gitignore enhanced
- Added .env/.env*, logs/, node_modules/, npm-debug.log*.

### 4. [x] Update TODO.md
- Marked steps 3-6 complete (dupe verify removed, changelog done, git verify via status, completion ready).

### 5. Verify: git status/diff
### 6. Test runserver + manual checks
### 7. attempt_completion

**Progress tracked here**
