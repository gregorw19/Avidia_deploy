from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pct", "0009_semester_hours_holidays"),
    ]

    operations = [
        migrations.AddField(
            model_name="availability",
            name="skills",
            field=models.ManyToManyField(blank=True, related_name="availabilities", to="pct.certificationtype"),
        ),
        migrations.AddField(
            model_name="shift",
            name="required_certifications",
            field=models.ManyToManyField(blank=True, related_name="shifts", to="pct.certificationtype"),
        ),
    ]
