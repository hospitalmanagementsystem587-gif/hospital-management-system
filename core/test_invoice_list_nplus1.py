from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from core.models import Invoice, Patient, Payment, PaymentMethod, StaffProfile
from core.roles import configure_role_permissions
from django.utils import timezone

class InvoiceListNPlus1Test(TestCase):
    def setUp(self):
        configure_role_permissions()

        self.user = User.objects.create_user(username="test_admin", password="password")
        self.staff_profile = StaffProfile.objects.create(user=self.user)
        group = Group.objects.get(name="Administrator")
        self.user.groups.add(group)
        self.client = Client()
        self.client.login(username="test_admin", password="password")

        self.patient = Patient.objects.create(
            mrn="MRN001",
            full_name="John Doe",
            date_of_birth="1990-01-01",
        )
        self.payment_method = PaymentMethod.objects.create(
            name="Cash",
            is_active=True
        )

        for i in range(15):
            invoice = Invoice.objects.create(
                number=f"INV-{i}",
                patient=self.patient,
                created_by=self.staff_profile,
                total=100.00
            )
            Payment.objects.create(
                receipt_number=f"RCT-{i}",
                invoice=invoice,
                amount=50.00,
                method=self.payment_method,
                received_by=self.staff_profile,
                received_at=timezone.now()
            )

    def test_invoice_list_queries(self):
        # Establish baseline: 1 (auth) + 1 (user) + 1 (staff) + 1 (invoices) + 15*3 (per invoice) = ~50 queries
        # With the fix, we expect < 15 queries total (14 based on output)
        with self.assertNumQueriesLessThan(15):
            response = self.client.get(reverse('invoice_list'))
            self.assertEqual(response.status_code, 200)

    def assertNumQueriesLessThan(self, num, *args, **kwargs):
        from django.db import connection
        return CaptureQueriesContextLessThan(connection, num)

class CaptureQueriesContextLessThan(object):
    def __init__(self, connection, limit):
        from django.test.utils import CaptureQueriesContext
        self.context = CaptureQueriesContext(connection)
        self.limit = limit

    def __enter__(self):
        self.context.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.context.__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return
        executed = len(self.context.captured_queries)
        if executed >= self.limit:
            raise AssertionError(
                f"Expected less than {self.limit} queries, but {executed} were executed."
            )
