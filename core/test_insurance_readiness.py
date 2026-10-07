from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from core.models import InsurancePolicy, InsuranceProvider, InsuranceVerification, Patient


class InsuranceReadinessTests(TransactionTestCase):
    def setUp(self):
        self.patient = Patient.objects.create(mrn="INS-1", full_name="Policy Owner")
        self.other = Patient.objects.create(mrn="INS-2", full_name="Other Owner")
        self.provider = InsuranceProvider.objects.create(code="SANDBOX", name="Sandbox insurer", provider_type="insurer")

    def test_multiple_policies_remain_patient_scoped(self):
        for suffix in ("A", "B"):
            InsurancePolicy.objects.create(patient=self.patient, provider=self.provider, member_reference=f"M-{suffix}", policy_reference=f"P-{suffix}", effective_from=date.today())
        InsurancePolicy.objects.create(patient=self.other, provider=self.provider, member_reference="OTHER", policy_reference="OTHER", effective_from=date.today())
        self.assertEqual(self.patient.insurance_policies.count(), 2)
        self.assertEqual(self.other.insurance_policies.count(), 1)

    def test_verified_result_requires_authority_actor_reference_and_time(self):
        policy = InsurancePolicy.objects.create(patient=self.patient, provider=self.provider, member_reference="M", policy_reference="P", effective_from=date.today())
        with self.assertRaises(IntegrityError), transaction.atomic():
            InsuranceVerification.objects.create(policy=policy, result="verified")
        actor = get_user_model().objects.create_user("tpa-operator")
        result = InsuranceVerification.objects.create(policy=policy, result="verified", authoritative_source="insurer-api", authority_reference="AUTH-1", performed_by=actor, performed_at=timezone.now())
        self.assertEqual(result.result, "verified")
