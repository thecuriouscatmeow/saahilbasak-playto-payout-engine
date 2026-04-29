import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("merchants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="api_key",
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
