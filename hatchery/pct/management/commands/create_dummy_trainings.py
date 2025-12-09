from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pct.models import CertificationLevel, CertificationType, Profile, Training


class Command(BaseCommand):
    help = "Creates dummy training sessions for quick testing"

    def handle(self, *args, **options):
        now = timezone.now()
        training_specs = [
            {
                "name": "Intro to 3D Printing",
                "machine": "Prusa MK4",
                "level": 1,
                "staff_username": "staff1",
                "student_username": None,
                "time": now + timedelta(days=2, hours=1),
                "cert_type": "3D Printing",
            },
            {
                "name": "Advanced 3D Printing",
                "machine": "Bambu Lab X1 Carbon",
                "level": 2,
                "staff_username": "staff2",
                "student_username": "student3",
                "time": now + timedelta(days=5, hours=2),
                "cert_type": "3D Printing",
            },
            {
                "name": "Laser Cutter Orientation",
                "machine": "Glowforge Pro",
                "level": 1,
                "staff_username": "staff3",
                "student_username": None,
                "time": now + timedelta(days=3, hours=5),
                "cert_type": "Laser Cutting",
            },
            {
                "name": "Woodshop Safety",
                "machine": "SawStop PCS",
                "level": 1,
                "staff_username": "staff4",
                "student_username": "student5",
                "time": now - timedelta(days=2),
                "cert_type": "Woodworking",
            },
            {
                "name": "Vinyl Cutter Basics",
                "machine": "Cricut Maker 3",
                "level": 1,
                "staff_username": "staff5",
                "student_username": None,
                "time": None,
                "cert_type": "Vinyl Cutting",
            },
            {
                "name": "Metal Lathe Training",
                "machine": "Precision Matthews PM-1236",
                "level": 3,
                "staff_username": "staff6",
                "student_username": "student9",
                "time": now + timedelta(days=10),
                "cert_type": "Metalworking",
            },
            {
                "name": "Electronics Soldering Lab",
                "machine": "Hakko FX-888D",
                "level": 2,
                "staff_username": "staff7",
                "student_username": None,
                "time": now + timedelta(days=1, hours=3),
                "cert_type": "Electronics",
            },
            {
                "name": "Textile Lab Orientation",
                "machine": "Juki TL-2010Q",
                "level": 1,
                "staff_username": "staff8",
                "student_username": "student12",
                "time": now + timedelta(days=4, hours=4),
                "cert_type": "Textiles",
            },
        ]

        # Make the level obvious in each title so seeded data is self-documenting.
        for spec in training_specs:
            spec["name"] = f"{spec['name']} (L{spec['level']})"

        created_count = 0
        skipped_count = 0

        for spec in training_specs:
            staff_profile = (
                Profile.objects.filter(user__username=spec["staff_username"], role="staff")
                .select_related("user")
                .first()
            )
            if staff_profile is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping '{spec['name']}' — staff '{spec['staff_username']}' not found."
                    )
                )
                skipped_count += 1
                continue

            student_profile = None
            student_username = spec.get("student_username")
            if student_username:
                student_profile = (
                    Profile.objects.filter(user__username=student_username, role__in=Profile.USER_ROLES)
                    .select_related("user")
                    .first()
                )
                if student_profile is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping student '{student_username}' for '{spec['name']}' — profile not found."
                        )
                    )

            level_obj = CertificationLevel.objects.filter(level=spec["level"]).first()
            if level_obj is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping '{spec['name']}' — certification level {spec['level']} missing."
                    )
                )
                skipped_count += 1
                continue

            if Training.objects.filter(name=spec["name"], staff=staff_profile).exists():
                self.stdout.write(
                    f"Training '{spec['name']}' for {staff_profile.user.username} already exists, skipping..."
                )
                skipped_count += 1
                continue

            cert_type_obj = None
            cert_type_name = spec.get("cert_type")
            if cert_type_name:
                cert_type_obj = CertificationType.objects.filter(name=cert_type_name).first()
                if cert_type_obj is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Certification type '{cert_type_name}' not found for '{spec['name']}'. Leaving blank."
                        )
                    )

            Training.objects.create(
                name=spec["name"],
                machine=spec["machine"],
                level=level_obj,
                certification_type=cert_type_obj,
                staff=staff_profile,
                student=student_profile,
                time=spec["time"],
            )
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Created training '{spec['name']}' with {staff_profile.get_full_name()}."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFinished creating dummy trainings. Added {created_count}, skipped {skipped_count}."
            )
        )
