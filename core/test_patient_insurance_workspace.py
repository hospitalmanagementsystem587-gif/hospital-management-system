from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    AbhaIntegrationConsent,
    InsurancePolicy,
    InsuranceProvider,
    InsuranceVerification,
    Patient,
    PatientAccount,
)
from core.roles import configure_role_permissions

User = get_user_model()


@override_settings(
    PORTAL_HOSTS={
        "admin": "admin.hms.test",
        "staff": "staff.hms.test",
        "store": "store.hms.test",
        "patient": "patient.hms.test",
        "agent": "agent.hms.test",
    },
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PatientInsuranceWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Patient 1: Alice (verified)
        cls.alice_user = User.objects.create_user(
            "alice_ins",
            email="alice@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Gupta",
        )
        cls.alice_patient = Patient.objects.create(
            mrn="MRN-ALICE-INS-01",
            full_name="Alice Gupta",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 28),
            phone="9876543210",
            email="alice@example.com",
        )
        cls.alice_account = PatientAccount.objects.create(
            user=cls.alice_user,
            patient=cls.alice_patient,
            is_verified=True,
        )

        # Patient 2: Bob (verified)
        cls.bob_user = User.objects.create_user(
            "bob_ins",
            email="bob@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Verma",
        )
        cls.bob_patient = Patient.objects.create(
            mrn="MRN-BOB-INS-01",
            full_name="Bob Verma",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 32),
            phone="9876543211",
            email="bob@example.com",
        )
        cls.bob_account = PatientAccount.objects.create(
            user=cls.bob_user,
            patient=cls.bob_patient,
            is_verified=True,
        )

        # Providers
        cls.provider_star = InsuranceProvider.objects.create(
            name="Star Health Allied Insurance",
            code="STAR-01",
            provider_type="insurer",
        )
        cls.provider_medi = InsuranceProvider.objects.create(
            name="MediAssist TPA",
            code="MEDI-TPA-01",
            provider_type="tpa",
        )

        # Staff Verifier
        cls.verifier_user = User.objects.create_user("tpa_verifier", password="password")

        # Alice Policies
        cls.alice_policy_1 = InsurancePolicy.objects.create(
            patient=cls.alice_patient,
            provider=cls.provider_star,
            policy_reference="POL-SECRET-STAR-123456",
            member_reference="MEM-SECRET-ALICE-9876",
            effective_from=date.today() - timedelta(days=100),
            effective_until=date.today() + timedelta(days=265),
            status=InsurancePolicy.Status.VERIFIED,
        )
        InsuranceVerification.objects.create(
            policy=cls.alice_policy_1,
            result="verified",
            authoritative_source="Star-API-Sandbox",
            authority_reference="AUTH-STAR-999",
            performed_by=cls.verifier_user,
            performed_at=timezone.now() - timedelta(days=90),
        )

        cls.alice_policy_2 = InsurancePolicy.objects.create(
            patient=cls.alice_patient,
            provider=cls.provider_medi,
            policy_reference="POL-PENDING-MEDI-7890",
            member_reference="MEM-PENDING-ALICE-1122",
            effective_from=date.today() - timedelta(days=10),
            status=InsurancePolicy.Status.UNVERIFIED,
        )

        # Alice ABHA Consents
        cls.alice_consent_active = AbhaIntegrationConsent.objects.create(
            patient=cls.alice_patient,
            consent_reference="ABHA-CONSENT-REF-88776655",
            purpose="Care Context Linking and Health Records Exchange",
            granted_at=timezone.now() - timedelta(days=5),
            expires_at=timezone.now() + timedelta(days=360),
            external_link_reference="EXT-LINK-ABHA-1234",
        )
        cls.alice_consent_revoked = AbhaIntegrationConsent.objects.create(
            patient=cls.alice_patient,
            consent_reference="ABHA-REVOKED-REF-11223344",
            purpose="Old Diagnostic Data Access",
            granted_at=timezone.now() - timedelta(days=30),
            expires_at=timezone.now() + timedelta(days=300),
            revoked_at=timezone.now() - timedelta(days=1),
        )

        # Bob Policy & Consent (cross-patient isolation)
        cls.bob_policy = InsurancePolicy.objects.create(
            patient=cls.bob_patient,
            provider=cls.provider_star,
            policy_reference="POL-BOB-CONFIDENTIAL-9999",
            member_reference="MEM-BOB-CONFIDENTIAL-8888",
            effective_from=date.today(),
            status=InsurancePolicy.Status.VERIFIED,
        )
        cls.bob_consent = AbhaIntegrationConsent.objects.create(
            patient=cls.bob_patient,
            consent_reference="ABHA-BOB-CONSENT-9999",
            purpose="Bob ABDM Exchange",
            granted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get("/insurance/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unverified_patient_cannot_view_insurance(self):
        self.alice_account.is_verified = False
        self.alice_account.save(update_fields=["is_verified"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/insurance/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_cannot_view_insurance(self):
        self.alice_patient.archived_at = timezone.now()
        self.alice_patient.save(update_fields=["archived_at"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/insurance/")
        self.assertEqual(resp.status_code, 403)

    def test_insurance_workspace_lists_policies_and_masks_sensitive_identifiers(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/insurance/")
        self.assertEqual(resp.status_code, 200)

        # Alice's providers are shown
        self.assertContains(resp, "Star Health Allied Insurance")
        self.assertContains(resp, "MediAssist TPA")

        # Masking verification: unmasked secrets must NOT appear
        self.assertNotContains(resp, "POL-SECRET-STAR-123456")
        self.assertNotContains(resp, "MEM-SECRET-ALICE-9876")
        self.assertNotContains(resp, "POL-PENDING-MEDI-7890")
        self.assertNotContains(resp, "MEM-PENDING-ALICE-1122")

        # Masked representations must appear (last 4 characters preserved)
        self.assertContains(resp, "3456")  # ends with 3456
        self.assertContains(resp, "9876")  # ends with 9876
        self.assertContains(resp, "7890")  # ends with 7890
        self.assertContains(resp, "1122")  # ends with 1122

        # Verification source badge
        self.assertContains(resp, "Source Verified")
        self.assertContains(resp, "Star-API-Sandbox")

        # Bob's policies must NOT leak
        self.assertNotContains(resp, "POL-BOB-CONFIDENTIAL-9999")
        self.assertNotContains(resp, "MEM-BOB-CONFIDENTIAL-8888")

    def test_abha_consents_listed_and_masked(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/insurance/")
        self.assertEqual(resp.status_code, 200)

        # Consents listed
        self.assertContains(resp, "Care Context Linking and Health Records Exchange")
        self.assertContains(resp, "Old Diagnostic Data Access")

        # Masking
        self.assertNotContains(resp, "ABHA-CONSENT-REF-88776655")
        self.assertNotContains(resp, "EXT-LINK-ABHA-1234")
        self.assertContains(resp, "6655")
        self.assertContains(resp, "1234")

        # Status badges
        self.assertContains(resp, "Active Consent")
        self.assertContains(resp, "Revoked")

        # Bob's ABHA consent must NOT leak
        self.assertNotContains(resp, "Bob ABDM Exchange")
        self.assertNotContains(resp, "ABHA-BOB-CONSENT-9999")
