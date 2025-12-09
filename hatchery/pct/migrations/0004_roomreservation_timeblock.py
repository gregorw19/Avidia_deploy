from django.db import migrations, models
import django.utils.timezone


def copy_start_to_end(apps, schema_editor):
    RoomReservation = apps.get_model("pct", "RoomReservation")
    for reservation in RoomReservation.objects.all().order_by("pk"):
        reservation.end_time = reservation.start_time
        reservation.save(update_fields=["end_time"])


def copy_end_to_start(apps, schema_editor):
    RoomReservation = apps.get_model("pct", "RoomReservation")
    for reservation in RoomReservation.objects.all().order_by("pk"):
        reservation.start_time = reservation.end_time
        reservation.save(update_fields=["start_time"])


class Migration(migrations.Migration):

    dependencies = [
        ("pct", "0003_roomreservation_update"),
    ]

    operations = [
        migrations.RenameField(
            model_name="roomreservation",
            old_name="reservation_time",
            new_name="start_time",
        ),
        migrations.AddField(
            model_name="roomreservation",
            name="end_time",
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(copy_start_to_end, copy_end_to_start),
        migrations.AlterModelOptions(
            name="roomreservation",
            options={"ordering": ["-start_time", "-created_at"]},
        ),
    ]
