import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import Component
from requests_app.models import BorrowItem, BorrowRequest
from users.models import APIToken, Group, GroupMember, Profile


def make_user(username: str, role: str, email: str | None = None) -> User:
    user = User.objects.create_user(
        username=username,
        password='pass1234',
        email=email or f'{username}@example.com',
    )
    profile = user.profile
    profile.role = role
    profile.full_name = username.title()
    profile.save(update_fields=['role', 'full_name'])
    return user


class ApiAccessTests(TestCase):
    def setUp(self):
        self.admin = make_user('api_admin', Profile.ROLE_ADMIN)
        self.faculty = make_user('api_faculty', Profile.ROLE_FACULTY)
        self.student = make_user('api_student', Profile.ROLE_STUDENT)
        self.component = Component.objects.create(
            name='Raspberry Pi',
            category='Boards',
            total_stock=5,
            available_stock=3,
        )

    def _issue_token(self, identity: str, password: str = 'pass1234'):
        response = self.client.post(
            reverse('api_issue_token'),
            data=json.dumps({'identity': identity, 'password': password}),
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['token']

    def test_issue_token_accepts_email_identity(self):
        token = self._issue_token(self.admin.email)
        self.assertTrue(token)

    def test_issue_token_rejects_ambiguous_full_name(self):
        u1 = make_user('same_name_1', Profile.ROLE_FACULTY, email='same1@example.com')
        u2 = make_user('same_name_2', Profile.ROLE_FACULTY, email='same2@example.com')
        u1.profile.full_name = 'Same Person'
        u2.profile.full_name = 'Same Person'
        u1.profile.save(update_fields=['full_name'])
        u2.profile.save(update_fields=['full_name'])

        response = self.client.post(
            reverse('api_issue_token'),
            data=json.dumps({'identity': 'Same Person', 'password': 'pass1234'}),
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Multiple accounts use this full name', response.json().get('error', ''))

    def test_components_endpoint_requires_token(self):
        response = self.client.get(reverse('api_components'), secure=True)
        self.assertEqual(response.status_code, 401)

    def test_me_endpoint_returns_profile_payload(self):
        token = self._issue_token(self.student.username)
        response = self.client.get(
            reverse('api_me'),
            HTTP_AUTHORIZATION=f'Token {token}',
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()['user']
        self.assertEqual(payload['username'], self.student.username)
        self.assertEqual(payload['role'], Profile.ROLE_STUDENT)

    def test_student_requests_are_group_scoped(self):
        teammate = make_user('api_teammate', Profile.ROLE_STUDENT)
        group = Group.objects.create(code='APIGRP', name='API Team', faculty=self.faculty)
        GroupMember.objects.create(group=group, user=self.student, role=GroupMember.ROLE_LEADER)
        GroupMember.objects.create(group=group, user=teammate, role=GroupMember.ROLE_MEMBER)
        self.student.profile.group_id = group.code
        self.student.profile.save(update_fields=['group_id'])
        teammate.profile.group_id = group.code
        teammate.profile.save(update_fields=['group_id'])

        own = BorrowRequest.objects.create(user=self.student, faculty=self.faculty, group=group)
        teammate_req = BorrowRequest.objects.create(user=teammate, faculty=self.faculty, group=group)
        BorrowItem.objects.create(borrow_request=own, component=self.component, quantity=1)
        BorrowItem.objects.create(borrow_request=teammate_req, component=self.component, quantity=2)

        token = self._issue_token(self.student.username)
        response = self.client.get(
            reverse('api_borrow_requests'),
            HTTP_AUTHORIZATION=f'Token {token}',
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        returned_ids = {row['id'] for row in response.json()['requests']}
        self.assertEqual(returned_ids, {own.id, teammate_req.id})

    @override_settings(API_TOKEN_ISSUE_RATE_LIMIT=1, AUTH_RATE_LIMIT_WINDOW_SECONDS=600)
    def test_issue_token_rate_limit_blocks_repeated_failures(self):
        cache.clear()
        first = self.client.post(
            reverse('api_issue_token'),
            data=json.dumps({'identity': 'ratelimit_user@example.com', 'password': 'wrong-pass'}),
            content_type='application/json',
            secure=True,
        )
        second = self.client.post(
            reverse('api_issue_token'),
            data=json.dumps({'identity': 'ratelimit_user@example.com', 'password': 'wrong-pass'}),
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)

    @override_settings(API_TOKEN_IDLE_TIMEOUT_SECONDS=1)
    def test_expired_idle_token_is_rejected(self):
        token = self._issue_token(self.admin.username)
        APIToken.objects.filter(key=token).update(last_used_at=timezone.now() - timedelta(seconds=5))
        response = self.client.get(
            reverse('api_me'),
            HTTP_AUTHORIZATION=f'Token {token}',
            secure=True,
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn('expired', response.json().get('error', '').lower())
