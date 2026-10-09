from pathlib import Path

from django.test import SimpleTestCase


class SupabaseRLSBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.apply_sql = (self.root / "db/security/kan_99_apply_rls.sql").read_text()
        self.verify_sql = (self.root / "db/security/kan_99_verify_rls.sql").read_text()

    def test_policy_is_fail_closed_for_browser_roles_and_explicit_for_django(self):
        self.assertIn("REVOKE ALL ON TABLE", self.apply_sql)
        self.assertIn("FROM anon, authenticated", self.apply_sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", self.apply_sql)
        self.assertIn("hms.django_role", self.apply_sql)
        self.assertIn("TO %I USING (true) WITH CHECK (true)", self.apply_sql)
        self.assertNotIn("to public", self.apply_sql.lower())

    def test_verifier_detects_disabled_rls_missing_policies_and_browser_grants(self):
        self.assertIn("RLS_DISABLED", self.verify_sql)
        self.assertIn("NO_USABLE_POLICY", self.verify_sql)
        self.assertIn("BROWSER_ROLE_HAS_TABLE_GRANT", self.verify_sql)
        self.assertIn("pg_policies", self.verify_sql)

    def test_kan_100_function_is_not_modified(self):
        self.assertNotIn("CREATE FUNCTION rls_auto_enable", self.apply_sql)
        self.assertNotIn("DROP FUNCTION rls_auto_enable", self.apply_sql)
