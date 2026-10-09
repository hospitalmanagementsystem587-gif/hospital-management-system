from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from core.models import Department, Patient, SLALog, SLAPolicy, StaffProfile, Ticket

User = get_user_model()


class TicketSLATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept_billing = Department.objects.create(name="Billing Dept", code="BILLING_SLA")
        cls.dept_pharmacy = Department.objects.create(name="Pharmacy Dept", code="PHARM_SLA")

        cls.agent_user = User.objects.create_user("sla_agent", password="testpassword123")
        perms = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=["view_ticket", "change_ticket"],
        )
        cls.agent_user.user_permissions.add(*perms)
        cls.agent_profile = StaffProfile.objects.create(
            user=cls.agent_user,
            employee_id="SLA-001",
            department=cls.dept_billing,
        )

        cls.patient = Patient.objects.create(mrn="PAT-SLA-01", full_name="SLA Patient")

        # Configurable SLA policies
        cls.urgent_policy = SLAPolicy.objects.create(
            name="Urgent Global SLA",
            priority=Ticket.Priority.URGENT,
            resolution_time_minutes=60,  # 1 hour
            is_active=True,
        )
        cls.billing_normal_policy = SLAPolicy.objects.create(
            name="Billing Normal SLA",
            category=Ticket.Category.BILLING,
            priority=Ticket.Priority.NORMAL,
            resolution_time_minutes=240,  # 4 hours
            is_active=True,
        )
        cls.billing_dept_policy = SLAPolicy.objects.create(
            name="Billing Department Specific SLA",
            department=cls.dept_billing,
            priority=Ticket.Priority.HIGH,
            resolution_time_minutes=120,  # 2 hours
            is_active=True,
        )

    def test_sla_target_determined_by_policy_hierarchy(self):
        # 1. Urgent priority matches urgent global policy (60 mins)
        t1 = Ticket.objects.create(
            title="Urgent request",
            description="Needs fast response",
            created_by=self.agent_user,
            priority=Ticket.Priority.URGENT,
            category=Ticket.Category.GENERAL,
        )
        self.assertEqual(t1.sla_policy, self.urgent_policy)
        self.assertIsNotNone(t1.sla_due_at)
        delta_seconds = abs((t1.sla_due_at - (t1.created_at + timedelta(minutes=60))).total_seconds())
        self.assertLess(delta_seconds, 1.0)

        # 2. Category Billing + Normal priority matches billing_normal_policy (240 mins)
        t2 = Ticket.objects.create(
            title="Invoice query",
            description="Clarification on charges",
            created_by=self.agent_user,
            priority=Ticket.Priority.NORMAL,
            category=Ticket.Category.BILLING,
        )
        self.assertEqual(t2.sla_policy, self.billing_normal_policy)
        delta_seconds_t2 = abs((t2.sla_due_at - (t2.created_at + timedelta(minutes=240))).total_seconds())
        self.assertLess(delta_seconds_t2, 1.0)

    def test_sla_recalculates_when_assigned_team_changes(self):
        t = Ticket.objects.create(
            title="High billing ticket",
            description="Important question",
            created_by=self.agent_user,
            priority=Ticket.Priority.HIGH,
            category=Ticket.Category.GENERAL,
        )
        # Assign to billing department which has billing_dept_policy (120 mins)
        t.assign(
            team=self.dept_billing,
            actor=self.agent_user,
            reason="Routing to Billing team",
        )
        t.refresh_from_db()
        self.assertEqual(t.sla_policy, self.billing_dept_policy)
        delta = abs((t.sla_due_at - (t.created_at + timedelta(minutes=120))).total_seconds())
        self.assertLess(delta, 1.0)

        # Check SLA log was created
        log = SLALog.objects.filter(ticket=t).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.agent_user)
        self.assertEqual(log.new_due_at, t.sla_due_at)

    def test_sla_clock_pause_and_resume_on_waiting_status(self):
        t = Ticket.objects.create(
            title="Test Pause",
            description="Needs info",
            created_by=self.agent_user,
            priority=Ticket.Priority.URGENT,
        )
        initial_due = t.sla_due_at

        # Transition to WAITING_ON_REQUESTER pauses the clock
        t.transition_to(
            Ticket.Status.WAITING_ON_REQUESTER,
            actor=self.agent_user,
            reason="Waiting for patient docs",
        )
        t.refresh_from_db()
        self.assertIsNotNone(t.sla_paused_at)
        pause_log = SLALog.objects.filter(ticket=t, event=SLALog.Event.CLOCK_PAUSED).first()
        self.assertIsNotNone(pause_log)

        # Simulate time passing while paused
        simulated_pause_time = timezone.now() - timedelta(minutes=30)
        Ticket.objects.filter(pk=t.pk).update(sla_paused_at=simulated_pause_time)
        t.refresh_from_db()

        # Resume to IN_PROGRESS extends due time by paused duration (~30 mins)
        t.transition_to(
            Ticket.Status.IN_PROGRESS,
            actor=self.agent_user,
            reason="Patient responded",
        )
        t.refresh_from_db()
        self.assertIsNone(t.sla_paused_at)
        self.assertGreaterEqual(t.sla_total_paused_seconds, 1790)  # ~1800s (30m)
        self.assertGreater(t.sla_due_at, initial_due)
        resume_log = SLALog.objects.filter(ticket=t, event=SLALog.Event.CLOCK_RESUMED).first()
        self.assertIsNotNone(resume_log)

    def test_sla_breach_detection_boundary(self):
        now = timezone.now()
        t = Ticket.objects.create(
            title="Breach test",
            description="Testing boundaries",
            created_by=self.agent_user,
            priority=Ticket.Priority.URGENT,
        )
        # Set due time in the past
        t.sla_due_at = now - timedelta(minutes=5)
        t.save(update_fields=["sla_due_at"])

        # Ticket should now evaluate as breached
        self.assertTrue(t.is_sla_breached)

        # Resolving after due time marks breach and records audit log
        t.transition_to(
            Ticket.Status.RESOLVED,
            actor=self.agent_user,
            reason="Resolved late",
        )
        t.refresh_from_db()
        self.assertIsNotNone(t.sla_breached_at)
        self.assertTrue(t.is_sla_breached)

        breach_log = SLALog.objects.filter(ticket=t, event=SLALog.Event.BREACHED).first()
        self.assertIsNotNone(breach_log)

    def test_sla_on_time_resolution_does_not_breach(self):
        now = timezone.now()
        t = Ticket.objects.create(
            title="On time test",
            description="Resolving promptly",
            created_by=self.agent_user,
            priority=Ticket.Priority.URGENT,
        )
        # Due time is 60 minutes in future
        self.assertFalse(t.is_sla_breached)

        t.transition_to(
            Ticket.Status.RESOLVED,
            actor=self.agent_user,
            reason="Completed early",
        )
        t.refresh_from_db()
        self.assertIsNone(t.sla_breached_at)
        self.assertFalse(t.is_sla_breached)
        self.assertFalse(SLALog.objects.filter(ticket=t, event=SLALog.Event.BREACHED).exists())
