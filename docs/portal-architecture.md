# HMS portal architecture (KAN-35)

## Boundary

The five browser portals are host-based entry points to the same Django
deployment and the same configured `DATABASES["default"]` PostgreSQL/Supabase
database:

| Host setting | Purpose | Initial server-side access policy |
| --- | --- | --- |
| `HMS_ADMIN_HOST` | Hospital management/CMS | Django staff/superuser (the native admin gate) |
| `HMS_STAFF_HOST` | Clinical/staff workspace | Administrator, Doctor, Reception, or Pharmacy group |
| `HMS_STORE_HOST` | Pharmacy/store | Administrator or Pharmacy group |
| `HMS_PATIENT_HOST` | Patient self-service | Verified `PatientAccount` whose patient is not archived |
| `HMS_AGENT_HOST` | Hospital support | Administrator only until a dedicated support role is approved |

`PortalRoutingMiddleware`, which runs after Django authentication, resolves only
exact configured hosts and selects a portal URLconf. It rejects authenticated
users outside the portal policy with HTTP 403. Anonymous users are sent to the
existing Django login. Navigation is not an authorization control; existing
view/model permission checks remain authoritative within a portal.

The existing server-rendered application remains available at its current host
for backwards compatibility and is also the initial staff workspace. KAN-35
does not add portal product features or redesign the CMS. Store, patient, and
agent roots are intentionally boundary markers for later tickets.

## API and identity compatibility

`/api/v1/` is deliberately host-neutral. Portal routing does not intercept it,
so the Android API paths, serializers, JWT authentication, permission classes,
and response contracts remain unchanged on every configured host. Browser
portals continue to use Django users, sessions, groups, and permissions.
Supabase Auth is not used.

No new database, backend, or domain model is introduced. There are no KAN-35
database migrations.

## Deployment

Set all five `HMS_*_HOST` values to exact DNS names and include those names in
`DJANGO_ALLOWED_HOSTS`. DNS/reverse-proxy entries must route each name to the
same Django service. Add matching HTTPS origins to
`DJANGO_CSRF_TRUSTED_ORIGINS` when portal forms are introduced. The middleware
does not trust client-supplied portal headers or query-string overrides.

Local defaults are `admin.localhost`, `staff.localhost`, `store.localhost`,
`patient.localhost`, and `agent.localhost`; Django accepts `.localhost` while
debugging.

## Shared Authentication & Session Layer (KAN-36)

- **Identity authority:** Django built-in auth (`django.contrib.auth`) remains the single identity authority.
- **Login & Logout:** Shared login at `/accounts/login/` via `HospitalLoginView` with failed login rate limiting (5 attempts per IP+username per 10 minutes), safe `next` parameter validation via `url_has_allowed_host_and_scheme`, and secure POST logout via Django's `LogoutView` at `/accounts/logout/`.
- **Session expiry:** Configurable via `DJANGO_SESSION_COOKIE_AGE` (defaults to 28,800s / 8h), expiring at browser close (`SESSION_EXPIRE_AT_BROWSER_CLOSE = True`).
- **Cookie & Subdomain Policy:** Cookies use `HttpOnly`, `SameSite=Lax`, and `Secure` when `DEBUG=False`. Cookie domains are configurable via `DJANGO_SESSION_COOKIE_DOMAIN` and `DJANGO_CSRF_COOKIE_DOMAIN` (e.g. `.example.com` for cross-subdomain single sign-on across `*.example.com`, or omitted/None for strict host-only session isolation).
- **Portal Context:** `request.portal` is set by `PortalRoutingMiddleware` and passed down to templates via `core.context_processors.hospital_context`.
