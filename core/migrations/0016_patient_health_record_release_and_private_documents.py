import uuid

import core.storage
from django.db import migrations, models
from django.db.models import Q


def populate_document_public_ids(apps, schema_editor):
    PatientDocument = apps.get_model("core", "PatientDocument")
    for document in PatientDocument.objects.filter(public_id__isnull=True).iterator():
        document.public_id = uuid.uuid4()
        document.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_patientaccount_id_document_reference_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="patient_released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="patient_access_revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="content_type",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="validation_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending malware scan"),
                    ("clean", "Validated clean"),
                    ("rejected", "Rejected"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="patient_released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="patientdocument",
            name="patient_access_revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="patientdocument",
            name="file",
            field=models.FileField(
                storage=core.storage.PrivatePatientDocumentStorage(),
                upload_to="patient_documents/%Y/%m/",
            ),
        ),
        migrations.RunPython(
            populate_document_public_ids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="patientdocument",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddConstraint(
            model_name="consultation",
            constraint=models.CheckConstraint(
                condition=(
                    Q(patient_access_revoked_at__isnull=True)
                    | Q(patient_released_at__isnull=False)
                ),
                name="consultation_revoke_after_release",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientdocument",
            constraint=models.CheckConstraint(
                condition=Q(validation_status__in=["pending", "clean", "rejected"]),
                name="patient_document_validation_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientdocument",
            constraint=models.CheckConstraint(
                condition=(
                    Q(patient_released_at__isnull=True)
                    | Q(validation_status="clean")
                ),
                name="patient_document_release_clean",
            ),
        ),
        migrations.AddConstraint(
            model_name="patientdocument",
            constraint=models.CheckConstraint(
                condition=(
                    Q(patient_access_revoked_at__isnull=True)
                    | Q(patient_released_at__isnull=False)
                ),
                name="patient_document_revoke_after_release",
            ),
        ),
    ]
