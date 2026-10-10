from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from core.models import Department, StaffProfile, Ticket

User = get_user_model()


class TicketAssignmentEngineTests(TestCase):
    def setUp(self):
        self.creator_user = User.objects.create_user(
            username="creator_user",
            email="creator@example.com",
            password="testpassword123",
        )
        self.staff_user1 = User.objects.create_user(
            username="staff_user1",
            first_name="Alice",
            last_name="Smith",
            email="staff1@example.com",
            password="testpassword123",
        )
        self.staff_user2 = User.objects.create_user(
            username="staff_user2",
            first_name="Bob",
            last_name="Jones",
            email="staff2@example.com",
            password="testpassword123",
        )
        self.actor_user = User.objects.create_user(
            username="actor_user",
            email="actor@example.com",
            password="testpassword123",
        )

        assignment_permissions = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=["view_ticket", "change_ticket"],
        )
        self.actor_user.user_permissions.add(*assignment_permissions)
        self.staff_user1.user_permissions.add(*assignment_permissions)
        self.staff_user2.user_permissions.add(*assignment_permissions)

        self.dept_billing = Department.objects.create(name="Billing Dept", code="BILLING_KAN89")
        self.dept_tech = Department.objects.create(name="IT Support", code="IT_KAN89")

        self.staff1 = StaffProfile.objects.create(
            user=self.staff_user1,
            employee_id="EMP-KAN89-01",
            department=self.dept_billing,
            job_title="Billing Specialist",
        )
        self.staff2 = StaffProfile.objects.create(
            user=self.staff_user2,
            employee_id="EMP-KAN89-02",
            department=self.dept_tech,
            job_title="IT Support Admin",
        )

        self.ticket = Ticket.objects.create(
            title="Billing discrepancy ticket",
            description="Patient observed billing discrepancy.",
            category=Ticket.Category.BILLING,
            priority=Ticket.Priority.NORMAL,
            created_by=self.creator_user,
        )

    def test_initial_ticket_is_unassigned(self):
        self.assertIsNone(self.ticket.assigned_to)
        self.assertIsNone(self.ticket.assigned_team)
        self.assertIsNone(self.ticket.assigned_at)

    def test_assign_to_staff_member(self):
        self.ticket.assign(staff_profile=self.staff1, actor=self.actor_user, reason="Assigned to billing specialist")
        self.ticket.refresh_from_db()

        self.assertEqual(self.ticket.assigned_to, self.staff1)
        self.assertIsNone(self.ticket.assigned_team)
        self.assertIsNotNone(self.ticket.assigned_at)

        # Confirm internal message was logged
        messages = self.ticket.messages.all()
        self.assertEqual(messages.count(), 1)
        msg = messages.first()
        self.assertTrue(msg.is_internal)
        self.assertEqual(msg.author, self.actor_user)
        self.assertIn("Assignment changed to", msg.body)
        self.assertIn("Assigned to billing specialist", msg.body)

    def test_assign_to_team(self):
        self.ticket.assign(team=self.dept_billing, actor=self.actor_user, reason="Escalated to Billing Team")
        self.ticket.refresh_from_db()

        self.assertIsNone(self.ticket.assigned_to)
        self.assertEqual(self.ticket.assigned_team, self.dept_billing)
        self.assertIsNotNone(self.ticket.assigned_at)

        msg = self.ticket.messages.first()
        self.assertTrue(msg.is_internal)
        self.assertIn("Billing Dept", msg.body)
        self.assertIn("Escalated to Billing Team", msg.body)

    def test_reassignment_to_new_staff_and_team(self):
        self.ticket.assign(staff_profile=self.staff1, team=self.dept_billing, actor=self.actor_user)
        initial_assigned_at = self.ticket.assigned_at

        # Reassign to staff2 and dept_tech
        self.ticket.assign(staff_profile=self.staff2, team=self.dept_tech, actor=self.actor_user, reason="Transferring to IT")
        self.ticket.refresh_from_db()

        self.assertEqual(self.ticket.assigned_to, self.staff2)
        self.assertEqual(self.ticket.assigned_team, self.dept_tech)
        self.assertGreaterEqual(self.ticket.assigned_at, initial_assigned_at)

        messages = self.ticket.messages.order_by("created_at")
        self.assertEqual(messages.count(), 2)
        latest_msg = messages.last()
        self.assertIn("Transferring to IT", latest_msg.body)
        self.assertIn("IT Support", latest_msg.body)

    def test_unassign_ticket(self):
        self.ticket.assign(staff_profile=self.staff1, team=self.dept_billing, actor=self.actor_user)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.assigned_at)

        # Unassign
        self.ticket.assign(staff_profile=None, team=None, actor=self.actor_user, reason="Returning to unassigned pool")
        self.ticket.refresh_from_db()

        self.assertIsNone(self.ticket.assigned_to)
        self.assertIsNone(self.ticket.assigned_team)
        self.assertIsNone(self.ticket.assigned_at)

        latest_msg = self.ticket.messages.order_by("created_at").last()
        self.assertIn("Unassigned", latest_msg.body)
        self.assertIn("Returning to unassigned pool", latest_msg.body)

    def test_direct_save_handles_assigned_at_lifecycle(self):
        # Direct save with assigned_to sets assigned_at
        self.ticket.assigned_to = self.staff1
        self.ticket.save()
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.assigned_at)

        # Clearing clears assigned_at
        self.ticket.assigned_to = None
        self.ticket.save()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assigned_at)
