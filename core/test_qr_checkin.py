from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Appointment, AuditEvent, Department, DigitalCheckInPass, Patient, PatientAccount, StaffProfile, VisitType


class SecureQrCheckInTests(TransactionTestCase):
    def setUp(self):
        user_model = get_user_model()
        department = Department.objects.create(code="QR", name="QR Reception")
        self.doctor_user = user_model.objects.create_user("qr-doctor")
        self.doctor = StaffProfile.objects.create(user=self.doctor_user, employee_id="QR-DOC", department=department)
        reception_group = Group.objects.create(name="Reception")
        self.reception_user = user_model.objects.create_user("qr-reception")
        self.reception_user.groups.add(reception_group)
        self.reception = StaffProfile.objects.create(user=self.reception_user, employee_id="QR-REC", department=department)
        self.patient = Patient.objects.create(mrn="QR-P1", full_name="QR Patient")
        self.patient_user = user_model.objects.create_user("qr-patient")
        PatientAccount.objects.create(user=self.patient_user, patient=self.patient, is_verified=True)
        self.other = Patient.objects.create(mrn="QR-P2", full_name="Other Patient")
        self.other_user = user_model.objects.create_user("qr-other")
        PatientAccount.objects.create(user=self.other_user, patient=self.other, is_verified=True)
        visit_type = VisitType.objects.create(code="QR-VISIT", name="QR Visit")
        self.appointment = Appointment.objects.create(patient=self.patient, doctor=self.doctor, visit_type=visit_type, scheduled_at=timezone.now(), status=Appointment.Status.SCHEDULED)
        self.other_appointment = Appointment.objects.create(patient=self.other, doctor=self.doctor, visit_type=visit_type, scheduled_at=timezone.now() + timedelta(minutes=30), status=Appointment.Status.SCHEDULED)

    def auth(self, client, user):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

    def issue(self):
        client = APIClient()
        self.auth(client, self.patient_user)
        return client.post("/api/v1/me/digital-pass/", {"appointment_id": self.appointment.pk}, format="json")

    def test_valid_pass_is_opaque_consumed_once_and_audited(self):
        issued = self.issue()
        self.assertEqual(issued.status_code, status.HTTP_200_OK)
        self.assertEqual(set(issued.json()), {"token", "expires_at", "appointment_id"})
        self.assertNotIn(self.patient.mrn, issued.json()["token"])
        reception = APIClient(); self.auth(reception, self.reception_user)
        consumed = reception.post("/api/v1/reception/qr-check-in/", {"token": issued.json()["token"]}, format="json")
        self.assertEqual(consumed.status_code, status.HTTP_200_OK)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CHECKED_IN)
        self.assertEqual(AuditEvent.objects.filter(action="appointment.qr_checked_in", actor=self.reception).count(), 1)
        replay = reception.post("/api/v1/reception/qr-check-in/", {"token": issued.json()["token"]}, format="json")
        self.assertEqual(replay.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(AuditEvent.objects.filter(action="appointment.qr_checked_in").count(), 1)

    def test_forged_expired_revoked_cross_patient_and_unauthorized_fail(self):
        issued = self.issue()
        token = issued.json()["token"]
        unauthenticated = APIClient().post("/api/v1/reception/qr-check-in/", {"token": token}, format="json")
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)
        reception = APIClient(); self.auth(reception, self.reception_user)
        self.assertEqual(reception.post("/api/v1/reception/qr-check-in/", {"token": "forged"}, format="json").status_code, 404)
        qr_pass = DigitalCheckInPass.objects.get(appointment=self.appointment)
        qr_pass.expires_at = timezone.now() - timedelta(seconds=1); qr_pass.save(update_fields=["expires_at"])
        self.assertEqual(reception.post("/api/v1/reception/qr-check-in/", {"token": token}, format="json").status_code, 404)
        other_client = APIClient(); self.auth(other_client, self.patient_user)
        cross = other_client.post("/api/v1/me/digital-pass/", {"appointment_id": self.other_appointment.pk}, format="json")
        self.assertEqual(cross.status_code, status.HTTP_409_CONFLICT)

    def test_refresh_revokes_previous_pass(self):
        first = self.issue().json()["token"]
        second = self.issue().json()["token"]
        reception = APIClient(); self.auth(reception, self.reception_user)
        self.assertEqual(reception.post("/api/v1/reception/qr-check-in/", {"token": first}, format="json").status_code, 404)
        self.assertEqual(reception.post("/api/v1/reception/qr-check-in/", {"token": second}, format="json").status_code, 200)
