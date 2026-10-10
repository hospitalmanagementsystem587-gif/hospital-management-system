from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from core.models import Department, Patient, PatientAccount, StaffProfile, Ticket
from core.roles import configure_role_permissions
from core.services.ticketing import agent_tickets_queryset

User = get_user_model()


class AgentQueueWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()
        cls.dept_it = Department.objects.create(name="IT Support", code="IT_AGENT")
        cls.dept_billing = Department.objects.create(name="Billing", code="BILLING_AGENT")

        # Create Agent 1 in IT Dept
        cls.agent1_user = User.objects.create_user("agent_it", password="password123")
        agent_group = Group.objects.get(name="Support Agent")
        cls.agent1_user.groups.add(agent_group)
        cls.agent1_profile = StaffProfile.objects.create(
            user=cls.agent1_user,
            employee_id="AGT-IT-01",
            department=cls.dept_it,
        )

        # Create Agent 2 in Billing Dept
        cls.agent2_user = User.objects.create_user("agent_billing", password="password123")
        cls.agent2_user.groups.add(agent_group)
        cls.agent2_profile = StaffProfile.objects.create(
            user=cls.agent2_user,
            employee_id="AGT-BIL-01",
            department=cls.dept_billing,
        )

        # Patient
        cls.patient = Patient.objects.create(mrn="PAT-AGT-01", full_name="Queue Patient")
        cls.patient_user = User.objects.create_user("queue_patient", password="password123")
        PatientAccount.objects.create(user=cls.patient_user, patient=cls.patient, is_verified=True)

        now = timezone.now()

        # Ticket 1: IT dept, unassigned
        cls.t_it_unassigned = Ticket.objects.create(
            title="Laptop malfunction",
            description="Hardware issue",
            created_by=cls.patient_user,
            patient=cls.patient,
            assigned_team=cls.dept_it,
            priority=Ticket.Priority.NORMAL,
        )

        # Ticket 2: IT dept, assigned to Agent 1
        cls.t_it_assigned = Ticket.objects.create(
            title="VPN issue",
            description="Connection dropping",
            created_by=cls.patient_user,
            patient=cls.patient,
            assigned_team=cls.dept_it,
            assigned_to=cls.agent1_profile,
            priority=Ticket.Priority.HIGH,
        )

        # Ticket 3: Billing dept, unassigned, SLA breached
        cls.t_billing_breached = Ticket.objects.create(
            title="Invoice dispute",
            description="Incorrect rate",
            created_by=cls.patient_user,
            patient=cls.patient,
            assigned_team=cls.dept_billing,
            priority=Ticket.Priority.URGENT,
            sla_due_at=now - timedelta(hours=2),
            sla_breached_at=now - timedelta(hours=2),
        )

    def test_agent_portal_access_authorization(self):
        # Support agent can access agent portal
        self.client.force_login(self.agent1_user)
        resp = self.client.get("/", HTTP_HOST="agent.localhost")
        self.assertEqual(resp.status_code, 200)

        # Regular patient cannot access agent portal
        self.client.force_login(self.patient_user)
        resp = self.client.get("/", HTTP_HOST="agent.localhost")
        self.assertEqual(resp.status_code, 403)

    def test_department_queue_scoping(self):
        # Agent 1 (IT) should only see IT tickets in their queue
        it_queue = agent_tickets_queryset(self.agent1_user, queue_filter="all")
        self.assertIn(self.t_it_unassigned, it_queue)
        self.assertIn(self.t_it_assigned, it_queue)
        self.assertNotIn(self.t_billing_breached, it_queue)

        # Agent 2 (Billing) should see billing tickets
        billing_queue = agent_tickets_queryset(self.agent2_user, queue_filter="all")
        self.assertIn(self.t_billing_breached, billing_queue)
        self.assertNotIn(self.t_it_unassigned, billing_queue)

    def test_queue_filters_work_deterministically(self):
        # Unassigned queue for IT
        unassigned = agent_tickets_queryset(self.agent1_user, queue_filter="unassigned")
        self.assertIn(self.t_it_unassigned, unassigned)
        self.assertNotIn(self.t_it_assigned, unassigned)

        # Assigned to me queue
        assigned_me = agent_tickets_queryset(self.agent1_user, queue_filter="assigned_to_me")
        self.assertIn(self.t_it_assigned, assigned_me)
        self.assertNotIn(self.t_it_unassigned, assigned_me)

        # High priority queue
        high_prio = agent_tickets_queryset(self.agent1_user, queue_filter="high_priority")
        self.assertIn(self.t_it_assigned, high_prio)
        self.assertNotIn(self.t_it_unassigned, high_prio)

        # SLA breached queue for Billing
        breached = agent_tickets_queryset(self.agent2_user, queue_filter="sla_breached")
        self.assertIn(self.t_billing_breached, breached)

    def test_agent_workspace_actions_and_notes(self):
        self.client.force_login(self.agent1_user)
        resp = self.client.get(f"/tickets/{self.t_it_assigned.pk}/", HTTP_HOST="agent.localhost")
        self.assertEqual(resp.status_code, 200)

        # Agent adds internal note
        post_data = {
            "action": "reply",
            "body": "Private troubleshooting note for IT staff",
            "is_internal": "true",
        }
        resp = self.client.post(f"/tickets/{self.t_it_assigned.pk}/", post_data, HTTP_HOST="agent.localhost")
        self.assertEqual(resp.status_code, 302)

        note = self.t_it_assigned.messages.filter(body="Private troubleshooting note for IT staff").first()
        self.assertIsNotNone(note)
        self.assertTrue(note.is_internal)
        self.assertEqual(note.author, self.agent1_user)

    def test_cross_department_workspace_access_denied(self):
        # Agent 1 (IT) attempts to directly access Billing ticket workspace
        self.client.force_login(self.agent1_user)
        resp = self.client.get(f"/tickets/{self.t_billing_breached.pk}/", HTTP_HOST="agent.localhost")
        self.assertEqual(resp.status_code, 403)
