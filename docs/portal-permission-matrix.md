# HMS portal permission matrix

All authorization is enforced by Django on the server. A visible link, portal
hostname, template condition, or knowledge of an object identifier never grants
access. Unknown portals and users without an explicitly allowed role fail closed.

| Portal | Admitted identities | Sensitive object boundary |
|---|---|---|
| Admin | active superuser, or active `is_staff` user | Django admin model permissions |
| Staff | Administrator, Doctor, Reception, Pharmacy | role permission plus doctor/patient, department, or operational relationship |
| Store | Administrator, Pharmacy | pharmacy permissions; no unrelated clinical/billing records |
| Patient | active verified PatientAccount whose Patient is not archived | self-access only |
| Agent | Administrator, Support Agent | ticket permission plus assignment/department scope |

## Role responsibilities

- Administrator: CMS and operational administration; sensitive actions still
  require their Django permission.
- Doctor: assigned clinical records and workflows only.
- Reception: registration, scheduling, authorized billing and operational work.
- Pharmacy: formulary, inventory, dispensing and pharmacy tickets only.
- Support Agent: operational tickets within its assignment/department scope;
  no general clinical or financial record access.
- Patient: no staff group. Access derives from the verified PatientAccount and
  is filtered to that Patient for every request.

## Sensitive domains

Patient documents remain private and are opened only after object authorization,
release/revocation checks and integrity validation. Prescriptions, invoices,
payments and tickets are filtered server-side. Ticket internal messages,
attachments and audit events are excluded from patient results. Android JWT APIs
retain their existing permission and patient-ownership checks.

The executable source of truth is `core.permission_matrix`,
`core.authorization.PORTAL_ALLOWED_GROUPS`, `core.roles.ROLE_PERMISSIONS`, and
the object-level services/querysets. Tests fail if their portal mappings diverge.
