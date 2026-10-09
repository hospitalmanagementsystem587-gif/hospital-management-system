import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0035_ticket_sla_breached_at_ticket_sla_due_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="TicketAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=64)),
                ("field", models.CharField(blank=True, max_length=64)),
                ("previous_value", models.JSONField(blank=True, null=True)),
                ("new_value", models.JSONField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("patient_visible", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ticket_audit_events", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_history", to="core.ticket")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "permissions": [("view_internal_ticketaudit", "Can view internal ticket audit history")],
                "indexes": [models.Index(fields=["ticket", "created_at"], name="ticket_audit_created_idx"), models.Index(fields=["ticket", "patient_visible"], name="ticket_audit_visible_idx")],
            },
        )
    ]
