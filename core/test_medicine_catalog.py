from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    AuditEvent,
    Consultation,
    Medicine,
    MedicineBatch,
    Patient,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    StockReceipt,
    Supplier,
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
class MedicineCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_med", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="DOC-MED-1"
        )

        cls.reception_user = User.objects.create_user("rec_med", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-MED-1"
        )

        cls.pharmacy_user = User.objects.create_user("pharm_med", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user, employee_id="PHM-MED-1"
        )

        cls.admin_user = User.objects.create_user(
            "admin_med", password="password", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-MED-1"
        )

        cls.ordinary_user = User.objects.create_user("ord_med", password="password")

        # Create sample medicines
        cls.med_active = Medicine.objects.create(
            code="MED-AMOX-500",
            generic_name="Amoxicillin",
            brand_name="Mox 500",
            strength="500 mg",
            dosage_form="Capsule",
            unit="capsule",
            barcode="8901234567890",
            is_otc=False,
            is_active=True,
        )
        cls.med_otc = Medicine.objects.create(
            code="MED-PARA-650",
            generic_name="Paracetamol",
            brand_name="Dolo 650",
            strength="650 mg",
            dosage_form="Tablet",
            unit="tablet",
            barcode="8909876543210",
            is_otc=True,
            is_active=True,
        )
        cls.med_inactive = Medicine.objects.create(
            code="MED-OLD-100",
            generic_name="Discontinued Antibiotic",
            brand_name="OldBrand",
            strength="100 mg",
            dosage_form="Tablet",
            unit="tablet",
            is_otc=False,
            is_active=False,
        )

    def test_anonymous_access_redirects_to_login(self):
        endpoints = [
            "/store/medicines/",
            "/store/medicines/create/",
            f"/store/medicines/{self.med_active.pk}/edit/",
        ]
        for url in endpoints:
            with self.subTest(url=url):
                res = self.client.get(url, HTTP_HOST="store.hms.test")
                self.assertRedirects(res, f"/accounts/login/?next={url}", fetch_redirect_response=False)

    def test_unauthorized_roles_receive_403(self):
        endpoints = [
            "/store/medicines/",
            "/store/medicines/create/",
            f"/store/medicines/{self.med_active.pk}/edit/",
        ]
        for user in (self.doctor_user, self.reception_user, self.ordinary_user):
            for url in endpoints:
                with self.subTest(user=user.username, url=url):
                    self.client.force_login(user)
                    res = self.client.get(url, HTTP_HOST="store.hms.test")
                    self.assertEqual(res.status_code, 403)

    def test_pharmacy_and_admin_can_view_medicine_list(self):
        for user in (self.pharmacy_user, self.admin_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                res = self.client.get("/store/medicines/", HTTP_HOST="store.hms.test")
                self.assertEqual(res.status_code, 200)
                self.assertContains(res, "Amoxicillin")
                self.assertContains(res, "Paracetamol")
                self.assertContains(res, "Discontinued Antibiotic")

    def test_medicine_search_and_status_filtering(self):
        self.client.force_login(self.pharmacy_user)

        # Search by generic name
        res_search = self.client.get("/store/medicines/?q=Amoxi", HTTP_HOST="store.hms.test")
        self.assertEqual(res_search.status_code, 200)
        self.assertContains(res_search, "Amoxicillin")
        self.assertNotContains(res_search, "Paracetamol")

        # Search by code
        res_code = self.client.get("/store/medicines/?q=MED-PARA", HTTP_HOST="store.hms.test")
        self.assertEqual(res_code.status_code, 200)
        self.assertContains(res_code, "Paracetamol")
        self.assertNotContains(res_code, "Amoxicillin")

        # Filter by active only
        res_active = self.client.get("/store/medicines/?status=active", HTTP_HOST="store.hms.test")
        self.assertEqual(res_active.status_code, 200)
        self.assertContains(res_active, "Amoxicillin")
        self.assertContains(res_active, "Paracetamol")
        self.assertNotContains(res_active, "Discontinued Antibiotic")

        # Filter by inactive only
        res_inactive = self.client.get("/store/medicines/?status=inactive", HTTP_HOST="store.hms.test")
        self.assertEqual(res_inactive.status_code, 200)
        self.assertContains(res_inactive, "Discontinued Antibiotic")
        self.assertNotContains(res_inactive, "Amoxicillin")

    def test_medicine_create_success_and_audit(self):
        self.client.force_login(self.pharmacy_user)
        payload = {
            "code": "MED-AZI-500",
            "generic_name": "Azithromycin",
            "brand_name": "Azee 500",
            "strength": "500 mg",
            "dosage_form": "Tablet",
            "unit": "strip",
            "barcode": "8901122334455",
            "is_otc": False,
            "is_active": True,
        }
        res = self.client.post("/store/medicines/create/", payload, HTTP_HOST="store.hms.test")
        self.assertRedirects(res, "/store/medicines/")

        med = Medicine.objects.get(code="MED-AZI-500")
        self.assertEqual(med.generic_name, "Azithromycin")
        self.assertEqual(med.brand_name, "Azee 500")
        self.assertEqual(med.unit, "strip")
        self.assertTrue(med.is_active)

        # Verify audit log
        audit = AuditEvent.objects.filter(
            target_type="medicine",
            target_id=str(med.pk),
            action="pharmacy.medicine_created",
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["code"], "MED-AZI-500")

    def test_medicine_create_duplicate_code_validation(self):
        self.client.force_login(self.pharmacy_user)
        payload = {
            "code": "MED-AMOX-500",  # Duplicate
            "generic_name": "Another Amoxicillin",
            "unit": "strip",
            "is_active": True,
        }
        res = self.client.post("/store/medicines/create/", payload, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertFormError(res.context["form"], "code", "A medicine with this code already exists.")

    def test_medicine_update_and_audit(self):
        self.client.force_login(self.admin_user)
        payload = {
            "code": self.med_active.code,
            "generic_name": "Amoxicillin Trihydrate",
            "brand_name": "Mox 500 Forte",
            "strength": "500 mg",
            "dosage_form": "Capsule",
            "unit": "capsule",
            "barcode": self.med_active.barcode,
            "is_otc": False,
            "is_active": True,
        }
        res = self.client.post(
            f"/store/medicines/{self.med_active.pk}/edit/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, "/store/medicines/")

        self.med_active.refresh_from_db()
        self.assertEqual(self.med_active.generic_name, "Amoxicillin Trihydrate")
        self.assertEqual(self.med_active.brand_name, "Mox 500 Forte")

        # Verify audit log
        audit = AuditEvent.objects.filter(
            target_type="medicine",
            target_id=str(self.med_active.pk),
            action="pharmacy.medicine_updated",
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("generic_name", audit.details["changed_fields"])
        self.assertIn("brand_name", audit.details["changed_fields"])

    def test_medicine_inactive_toggle_preserves_historical_records(self):
        """Preserves historical prescriptions and batches when medicine is deactivated."""
        patient = Patient.objects.create(mrn="PAT-HIST-01", full_name="Hist Patient")
        consult = Consultation.objects.create(
            doctor=self.doctor_profile,
            patient=patient,
            diagnosis="Infection",
        )
        rx = Prescription.objects.create(
            consultation=consult,
            patient=patient,
            doctor=self.doctor_profile,
            number="RX-HIST-01",
            status=Prescription.Status.ISSUED,
        )
        item = PrescriptionItem.objects.create(
            prescription=rx,
            medicine=self.med_active,
            dosage="500mg",
            frequency="TID",
            duration="5 days",
            quantity=Decimal("10.000"),
        )

        supplier = Supplier.objects.create(code="SUP-HIST", name="Supplier Hist")
        receipt = StockReceipt.objects.create(
            number="REC-HIST", supplier=supplier, received_at=timezone.now()
        )
        batch = MedicineBatch.objects.create(
            medicine=self.med_active,
            receipt=receipt,
            batch_number="BAT-HIST-01",
            expiry_date=timezone.localdate(),
            purchase_price=Decimal("10.00"),
            sale_price=Decimal("15.00"),
            quantity_received=Decimal("100"),
            quantity_on_hand=Decimal("50"),
        )

        # Soft disable the medicine
        self.client.force_login(self.pharmacy_user)
        payload = {
            "code": self.med_active.code,
            "generic_name": self.med_active.generic_name,
            "brand_name": self.med_active.brand_name,
            "strength": self.med_active.strength,
            "dosage_form": self.med_active.dosage_form,
            "unit": self.med_active.unit,
            "barcode": self.med_active.barcode,
            "is_otc": self.med_active.is_otc,
            "is_active": False,  # Deactivate
        }
        res = self.client.post(
            f"/store/medicines/{self.med_active.pk}/edit/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, "/store/medicines/")

        self.med_active.refresh_from_db()
        self.assertFalse(self.med_active.is_active)

        # Historical references remain intact
        item.refresh_from_db()
        self.assertEqual(item.medicine, self.med_active)
        batch.refresh_from_db()
        self.assertEqual(batch.medicine, self.med_active)
