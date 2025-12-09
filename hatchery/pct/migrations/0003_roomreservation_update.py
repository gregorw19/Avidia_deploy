from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pct", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoomReservation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "room",
                    models.CharField(
                        choices=[
                            ("second_hatch_front", "Second Floor • Hatch Front"),
                            ("second_hatch_back", "Second Floor • Hatch Back"),
                            ("third_proto_studio", "Third Floor • Prototyping Studio"),
                            ("third_proto_shop", "Third Floor • Prototyping Shop"),
                        ],
                        max_length=32,
                    ),
                ),
                ("reservation_time", models.DateTimeField()),
                (
                    "affiliation",
                    models.CharField(help_text="Class or organization", max_length=255),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("denied", "Denied"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requester",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="room_reservations",
                        to="pct.profile",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="room_reservations_reviewed",
                        to="pct.profile",
                    ),
                ),
            ],
            options={
                "ordering": ["-reservation_time", "-created_at"],
            },
        ),
    ]
