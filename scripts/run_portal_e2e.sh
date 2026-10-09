#!/usr/bin/env bash
set -euo pipefail

python manage.py test \
  core.test_portal_architecture \
  core.test_shared_auth_session \
  core.test_portal_authorization \
  core.test_object_level_access_matrix \
  core.test_patient_appointment_booking_workspace \
  core.test_consultation_workspace \
  core.test_prescription_workspace \
  core.test_dispensing_queue_workspace \
  core.test_pharmacy_sales_workspace \
  core.test_price_versions_effective_dates \
  core.test_invoice_price_snapshots \
  core.test_patient_ticketing \
  core.test_agent_queue \
  core.test_ticket_security \
  core.test_patient_api \
  core.test_supabase_rls_boundary

python manage.py check
python manage.py makemigrations --check --dry-run
