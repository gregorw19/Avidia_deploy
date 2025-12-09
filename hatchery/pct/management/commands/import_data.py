import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from pct.models import School, Major, Minor

class Command(BaseCommand):
    help = 'Import schools, majors, and minors from CSV files'

    def handle(self, *args, **kwargs):
        majors_path = os.path.join(settings.BASE_DIR, 'pct/script', 'schools_and_majors.csv')
        minors_path = os.path.join(settings.BASE_DIR, 'pct/script', 'minors.csv')

        # Import majors
        with open(majors_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                school, _ = School.objects.get_or_create(school_name=row['school_name'])
                Major.objects.get_or_create(major_name=row['major_name'], school=school)

        # Import minors
        with open(minors_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                print(f"Importing minor: {row['minor_name']}")
                Minor.objects.get_or_create(minor_name=row['minor_name'])

        self.stdout.write(self.style.SUCCESS('Data has been imported'))
