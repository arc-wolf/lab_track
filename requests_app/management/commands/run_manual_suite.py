import datetime
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import Component, Reservation
from requests_app.models import BorrowRequest, BorrowItem
from requests_app.tasks import send_due_reminders, update_overdue_requests
from users.models import Group, GroupMember, Profile


class Command(BaseCommand):
    help = "Runs a scripted sanity sweep mirroring key manual tests."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("run_manual_suite is restricted to DEBUG environments.")
        results = []

        with override_settings(SECURE_SSL_REDIRECT=False):
            self._run_suite(results)

    def _run_suite(self, results):
        def ok(label):
            results.append(f"OK  - {label}")

        def fail(label, err):
            results.append(f"FAIL- {label}: {err}")

        try:
            student = self._ensure_user("auto_student", "auto_student@am.students.amrita.edu", "Auto Student", Profile.ROLE_STUDENT)
            faculty = self._ensure_user("auto_faculty", "auto_faculty@am.amrita.edu", "Auto Faculty", Profile.ROLE_FACULTY)
            admin = self._ensure_user("auto_admin", "auto_admin@am.amrita.edu", "Auto Admin", Profile.ROLE_ADMIN)
            ok("Seed users")
        except Exception as exc:
            fail("Seed users", exc)
            self._print(results)
            return

        try:
            component = Component.objects.first()
            if not component:
                component = Component.objects.create(
                    name="Auto Component",
                    category="Auto",
                    total_stock=10,
                    available_stock=10,
                    student_limit=5,
                )
            ok(f"Component ready (id={component.id})")
        except Exception as exc:
            fail("Component availability", exc)
            self._print(results)
            return

        try:
            group = self._ensure_group(student, faculty)
            ok(f"Group linked ({group.code})")
        except Exception as exc:
            fail("Group link", exc)
            self._print(results)
            return

        client = Client()
        client.defaults["wsgi.url_scheme"] = "https"
        if not client.login(username=student.username, password="Passw0rd!"):
            fail("Student login", "invalid credentials")
            self._print(results)
            return
        ok("Student login")

        try:
            dash_resp = client.get(reverse("student_dashboard"))
            if dash_resp.status_code == 200:
                ok("Student dashboard load")
            else:
                fail("Student dashboard load", f"status={dash_resp.status_code} redirect={dash_resp.headers.get('Location')}")
        except Exception as exc:
            fail("Student dashboard load", exc)

        try:
            Reservation.objects.filter(user=student).delete()
            add_resp = client.post(reverse("add_to_cart", args=[component.id]), {"quantity": 1}, follow=True)
            created = Reservation.objects.filter(user=student, component=component, is_active=True).exists()
            if add_resp.status_code == 200 and created:
                ok("Add to cart")
            else:
                fail("Add to cart", f"status={add_resp.status_code} created={created}")
        except Exception as exc:
            fail("Add to cart", exc)

        try:
            slip_resp = client.post(
                reverse("generate_slip"),
                {"project_title": "Auto Project", "faculty": faculty.profile.id},
                follow=True,
            )
            slip = BorrowRequest.objects.filter(user=student).order_by("-id").first()
            if slip_resp.status_code == 200 and slip:
                ok(f"Slip generated (id={slip.id})")
            else:
                fail("Slip generation", f"status={slip_resp.status_code} slip={slip}")
        except Exception as exc:
            fail("Slip generation", exc)
            self._print(results)
            return

        try:
            pdf_resp = client.get(reverse("download_slip", args=[slip.id]))
            assert pdf_resp.status_code == 200
            assert pdf_resp["Content-Type"] == "application/pdf"
            ok("PDF download")
        except Exception as exc:
            fail("PDF download", exc)

        try:
            slip.due_date = timezone.now().date() + datetime.timedelta(days=5)
            slip.reminder_sent = False
            slip.status = BorrowRequest.STATUS_APPROVED
            slip.save(update_fields=["due_date", "reminder_sent", "status"])
            send_due_reminders()
            slip.refresh_from_db()
            assert slip.reminder_sent is True
            ok("Reminder task")
        except Exception as exc:
            fail("Reminder task", exc)

        try:
            slip.status = BorrowRequest.STATUS_ISSUED
            slip.due_date = timezone.now().date() - datetime.timedelta(days=1)
            slip.reminder_sent = True
            slip.save(update_fields=["status", "due_date", "reminder_sent"])
            update_overdue_requests()
            slip.refresh_from_db()
            assert slip.status == BorrowRequest.STATUS_OVERDUE
            ok("Overdue task")
        except Exception as exc:
            fail("Overdue task", exc)

        try:
            client.logout()
            if not client.login(username=admin.username, password="Passw0rd!"):
                raise RuntimeError("admin login failed")
            resp = client.get(reverse("admin_dashboard"))
            assert resp.status_code == 200
            ok("Admin dashboard load")
        except Exception as exc:
            fail("Admin dashboard load", exc)

        self._print(results)

    def _ensure_user(self, username, email, full_name, role):
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        if created:
            user.set_password("Passw0rd!")
        user.email = email
        user.save()
        profile = user.profile
        profile.role = role
        profile.full_name = full_name
        profile.save()
        if role == Profile.ROLE_ADMIN:
            user.is_staff = True
            user.is_superuser = False
            user.save()
        return user

    def _ensure_group(self, student, faculty):
        code = "AUTOGRP"
        group, _ = Group.objects.get_or_create(code=code, defaults={"name": "Auto Group", "faculty": faculty, "status": Group.STATUS_APPROVED})
        if group.faculty_id != faculty.id:
            group.faculty = faculty
            group.status = Group.STATUS_APPROVED
            group.save(update_fields=["faculty", "status"])
        prof = student.profile
        prof.group_id = code
        prof.group_name = group.name
        prof.faculty_incharge = faculty.username
        prof.save(update_fields=["group_id", "group_name", "faculty_incharge"])
        GroupMember.objects.get_or_create(group=group, user=student, defaults={"role": GroupMember.ROLE_LEADER})
        return group

    def _print(self, results):
        self.stdout.write("\nScripted sanity sweep results:")
        for line in results:
            self.stdout.write(line)
