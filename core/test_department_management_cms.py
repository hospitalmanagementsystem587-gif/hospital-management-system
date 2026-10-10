from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from core.models import Department, StaffProfile
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
    ALLOWED_HOSTS=["*"],
)
class DepartmentManagementCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()
        cls.admin_group = Group.objects.get(name="Administrator")
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.patient_group, _ = Group.objects.get_or_create(name="Patient")

    def setUp(self):
        # Create standard test users
        self.admin_user = User.objects.create_user(
            username="admin_dept_user",
            email="admin_dept@test.hms",
            password="StrongAdminPassword123!",
            is_staff=True,
        )
        self.admin_user.groups.add(self.admin_group)

        self.doctor_user = User.objects.create_user(
            username="doctor_dept_user",
            email="doctor_dept@test.hms",
            password="StrongDoctorPassword123!",
            is_staff=False,
        )
        self.doctor_user.groups.add(self.doctor_group)

        self.patient_user = User.objects.create_user(
            username="patient_dept_user",
            email="patient_dept@test.hms",
            password="StrongPatientPassword123!",
            is_staff=False,
        )
        self.patient_user.groups.add(self.patient_group)

        # Baseline department
        self.cardio_dept = Department.objects.create(
            code="CARDIO",
            name="Cardiology",
            description="Cardiovascular diseases and care.",
            icon_name="favorite",
            display_order=1,
            is_active=True,
        )

    def test_authorized_admin_can_view_department_changelist(self):
        """Staff with view_department permission can view department changelist."""
        self.client.force_login(self.admin_user)
        response = self.client.get(
            "/admin/core/department/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cardiology")
        self.assertContains(response, "CARDIO")

    def test_authorized_admin_can_create_department(self):
        """Administrator can create a new department with unique code and name."""
        self.client.force_login(self.admin_user)
        payload = {
            "code": "ortho",  # Should be normalized to uppercase ORTHO
            "name": "Orthopedics",
            "description": "Musculoskeletal system care.",
            "icon_name": "accessibility",
            "display_order": "2",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/department/add/",
            data=payload,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        dept = Department.objects.filter(code="ORTHO").first()
        self.assertIsNotNone(dept)
        self.assertEqual(dept.name, "Orthopedics")
        self.assertEqual(dept.display_order, 2)
        self.assertTrue(dept.is_active)

    def test_authorized_admin_can_edit_department(self):
        """Administrator can update existing department details."""
        self.client.force_login(self.admin_user)
        payload = {
            "code": "CARDIO",
            "name": "Advanced Cardiology",
            "description": "Comprehensive cardiac and vascular clinical services.",
            "icon_name": "heart_check",
            "display_order": "5",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(
            f"/admin/core/department/{self.cardio_dept.pk}/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.cardio_dept.refresh_from_db()
        self.assertEqual(self.cardio_dept.name, "Advanced Cardiology")
        self.assertEqual(self.cardio_dept.display_order, 5)
        self.assertEqual(self.cardio_dept.icon_name, "heart_check")

    def test_unauthenticated_request_redirected_to_login(self):
        """Unauthenticated requests redirect to shared login."""
        response = self.client.get(
            "/admin/core/department/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=/admin/core/department/", response.url)

    def test_unauthorized_portal_roles_denied(self):
        """Doctor and Patient roles cannot access department admin."""
        self.client.force_login(self.doctor_user)
        response = self.client.get(
            "/admin/core/department/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.patient_user)
        response = self.client.get(
            "/admin/core/department/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_without_change_permission_cannot_mutate_department(self):
        """Staff user with view-only permission cannot add or update departments."""
        view_only_user = User.objects.create_user(
            username="view_only_dept_staff",
            password="StrongStaffPassword123!",
            is_staff=True,
        )
        content_type = ContentType.objects.get_for_model(Department)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_department")
        view_only_user.user_permissions.add(view_perm)

        self.client.force_login(view_only_user)
        payload = {
            "code": "CARDIO",
            "name": "Tampered Name",
            "display_order": "1",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(
            f"/admin/core/department/{self.cardio_dept.pk}/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)
        self.cardio_dept.refresh_from_db()
        self.assertEqual(self.cardio_dept.name, "Cardiology")

    def test_duplicate_code_prevented(self):
        """Creating a department with an existing code (case-insensitive) is rejected."""
        self.client.force_login(self.admin_user)
        payload = {
            "code": "cardio",  # Existing code in lowercase
            "name": "Cardiac Surgery",
            "display_order": "3",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/department/add/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("code", form.errors)
        self.assertIn("Department with code 'CARDIO' already exists.", form.errors["code"])

    def test_duplicate_name_prevented(self):
        """Creating a department with an existing name (case-insensitive) is rejected."""
        self.client.force_login(self.admin_user)
        payload = {
            "code": "CAR-SURG",
            "name": "cardiology",  # Existing name in lowercase
            "display_order": "3",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/department/add/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("name", form.errors)
        self.assertIn("Department with name 'cardiology' already exists.", form.errors["name"])

    def test_deactivation_preserves_staff_and_historical_references(self):
        """Deactivating a department preserves StaffProfile foreign key references."""
        staff_doc = User.objects.create_user(
            username="cardiologist_user",
            password="DocPassword123!",
        )
        staff_profile = StaffProfile.objects.create(
            user=staff_doc,
            employee_id="DOC-CARDIO-001",
            department=self.cardio_dept,
            job_title="Senior Cardiologist",
        )

        # Deactivate department via admin POST
        self.client.force_login(self.admin_user)
        payload = {
            "code": "CARDIO",
            "name": "Cardiology",
            "description": "Cardiovascular diseases and care.",
            "icon_name": "favorite",
            "display_order": "1",
            # 'is_active' omitted to deactivate
            "_save": "Save",
        }
        response = self.client.post(
            f"/admin/core/department/{self.cardio_dept.pk}/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify department is now inactive
        self.cardio_dept.refresh_from_db()
        self.assertFalse(self.cardio_dept.is_active)

        # Verify StaffProfile relation remains intact
        staff_profile.refresh_from_db()
        self.assertEqual(staff_profile.department, self.cardio_dept)
        self.assertEqual(staff_profile.department.name, "Cardiology")

    def test_deactivation_hides_department_from_public_api(self):
        """Inactive departments are filtered out from public /api/v1/departments/ API."""
        # Active state: appears in public API
        res_active = self.client.get("/api/v1/departments/")
        self.assertEqual(res_active.status_code, 200)
        active_codes = [d["code"] for d in res_active.data]
        self.assertIn("CARDIO", active_codes)

        # Deactivate
        self.cardio_dept.is_active = False
        self.cardio_dept.save()

        # Inactive state: filtered out
        res_inactive = self.client.get("/api/v1/departments/")
        self.assertEqual(res_inactive.status_code, 200)
        inactive_codes = [d["code"] for d in res_inactive.data]
        self.assertNotIn("CARDIO", inactive_codes)

    def test_cannot_delete_department_with_active_staff_members(self):
        """Department with assigned staff members cannot be deleted."""
        staff_user = User.objects.create_user(
            username="staff_member",
            password="StaffPassword123!",
        )
        StaffProfile.objects.create(
            user=staff_user,
            employee_id="EMP-CARDIO-999",
            department=self.cardio_dept,
        )

        self.client.force_login(self.admin_user)
        response = self.client.post(
            f"/admin/core/department/{self.cardio_dept.pk}/delete/",
            HTTP_HOST="admin.hms.test",
        )
        # has_delete_permission returns False, giving HTTP 403
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Department.objects.filter(pk=self.cardio_dept.pk).exists())

    def test_can_delete_empty_department(self):
        """Department with no assigned staff can be deleted by authorized admin."""
        empty_dept = Department.objects.create(
            code="EMPTY",
            name="Empty Department",
        )
        self.client.force_login(self.admin_user)
        response = self.client.post(
            f"/admin/core/department/{empty_dept.pk}/delete/",
            data={"post": "yes"},
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Department.objects.filter(pk=empty_dept.pk).exists())

    def test_ordering_and_display_order_enforced(self):
        """Departments are listed according to display_order ascending."""
        dept_c = Department.objects.create(code="DEPT-C", name="C Dept", display_order=30)
        dept_a = Department.objects.create(code="DEPT-A", name="A Dept", display_order=10)
        dept_b = Department.objects.create(code="DEPT-B", name="B Dept", display_order=20)

        res = self.client.get("/api/v1/departments/")
        self.assertEqual(res.status_code, 200)
        ordered_codes = [d["code"] for d in res.data if d["code"].startswith("DEPT-")]
        self.assertEqual(ordered_codes, ["DEPT-A", "DEPT-B", "DEPT-C"])

    def test_xss_content_escaped(self):
        """Malicious script input in department name/description is escaped in rendered output."""
        self.client.force_login(self.admin_user)
        payload = {
            "code": "XSS-DEPT",
            "name": "Neurology <script>alert('xss')</script>",
            "description": "Brain <b onmouseover='alert(1)'>Care</b>",
            "icon_name": "psychology",
            "display_order": "1",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/department/add/",
            data=payload,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('xss')</script>")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")
