import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from core.models import PatientVerificationChallenge, Patient


class VerificationProvider:
    """
    Verification provider abstraction.
    In testing/dev environment, codes can be generated and queried via challenge objects.
    In production, this integrates with real SMS/Email gateways without logging codes.
    """

    CHALLENGE_VALIDITY = timedelta(minutes=10)
    MAX_ATTEMPTS = 3

    @staticmethod
    def _hash_code(code: str, salt: str) -> str:
        # PBKDF2 HMAC SHA-256 with 10,000 iterations to prevent OTP rainbow table / preimage attacks
        return hashlib.pbkdf2_hmac(
            "sha256",
            code.encode("utf-8"),
            salt.encode("utf-8"),
            10000,
        ).hex()

    @classmethod
    def create_challenge(cls, contact: str, purpose: str, matched_patient: Patient = None, fixed_code: str = None) -> tuple[PatientVerificationChallenge, str]:
        # Expire any active challenges for this contact & purpose
        PatientVerificationChallenge.objects.filter(
            contact=contact,
            purpose=purpose,
            is_used=False,
        ).update(is_used=True)

        raw_code = fixed_code or f"{secrets.randbelow(900000) + 100000}"
        salt = secrets.token_hex(16)
        code_hash = cls._hash_code(raw_code, salt)
        expires_at = timezone.now() + cls.CHALLENGE_VALIDITY

        challenge = PatientVerificationChallenge.objects.create(
            contact=contact,
            purpose=purpose,
            salt=salt,
            code_hash=code_hash,
            expires_at=expires_at,
            matched_patient=matched_patient,
        )
        return challenge, raw_code

    @classmethod
    def verify_challenge(cls, contact: str, purpose: str, code: str) -> tuple[bool, str, PatientVerificationChallenge]:
        challenge = (
            PatientVerificationChallenge.objects.filter(
                contact=contact,
                purpose=purpose,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if not challenge:
            return False, "No active verification challenge found.", None

        if timezone.now() > challenge.expires_at:
            challenge.is_used = True
            challenge.save(update_fields=["is_used", "updated_at"])
            return False, "Verification code has expired.", None

        if challenge.attempts_count >= cls.MAX_ATTEMPTS:
            challenge.is_used = True
            challenge.save(update_fields=["is_used", "updated_at"])
            return False, "Maximum verification attempts exceeded. Please request a new code.", None

        challenge.attempts_count += 1
        challenge.save(update_fields=["attempts_count", "updated_at"])

        salt = challenge.salt or ""
        if cls._hash_code(code, salt) != challenge.code_hash:
            return False, "Invalid verification code.", None

        challenge.is_used = True
        challenge.save(update_fields=["is_used", "updated_at"])
        return True, "Verified", challenge
