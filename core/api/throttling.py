from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonRateThrottle(AnonRateThrottle):
    scope = "auth_anon"


class AppointmentWriteRateThrottle(UserRateThrottle):
    scope = "appointment_write"
