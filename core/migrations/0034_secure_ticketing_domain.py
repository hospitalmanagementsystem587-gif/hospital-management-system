from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0033_ticket_assigned_at_ticket_assigned_team_and_more")]

    operations = [
        migrations.AddField(
            model_name="ticketattachment",
            name="is_internal",
            field=models.BooleanField(
                default=False,
                help_text="If true, only authorized hospital staff may access this attachment.",
            ),
        ),
        migrations.AlterField(
            model_name="ticketattachment",
            name="scan_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Scan"),
                    ("clean", "Validated Clean"),
                    ("rejected", "Rejected / Infected"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
