from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0036_ticketauditevent")]

    operations = [
        migrations.AlterModelOptions(
            name="auditevent",
            options={"ordering": ["created_at", "id"]},
        ),
    ]
