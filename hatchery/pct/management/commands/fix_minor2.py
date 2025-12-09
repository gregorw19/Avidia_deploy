from django.core.management.base import BaseCommand
from pct.models import Profile, Minor

class Command(BaseCommand):
    help = "Fix profiles with invalid minor2 foreign key"

    def handle(self, *args, **kwargs):
        broken_profiles = Profile.objects.exclude(minor2=None).exclude(minor2__in=Minor.objects.all())
        count = broken_profiles.count()

        for profile in broken_profiles:
            self.stdout.write(f"Fixing Profile ID {profile.id} with invalid minor2_id={profile.minor2_id}")
            profile.minor2 = None
            profile.save()

        self.stdout.write(self.style.SUCCESS(f"Fixed {count} profile(s)."))
