import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from pct.models import Profile, School, Major, Minor


class Command(BaseCommand):
    help = 'Creates dummy users with student and staff roles'

    def handle(self, *args, **options):
        # Create dummy students
        students = [
            {
                'username': 'student1',
                'email': 'student1@bc.edu',
                'first_name': 'John',
                'last_name': 'Smith',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student2',
                'email': 'student2@bc.edu',
                'first_name': 'Emily',
                'last_name': 'Johnson',
                'role': 'student',
                'major_count': 2,
                'minor_count': 0,
            },
            {
                'username': 'student3',
                'email': 'student3@bc.edu',
                'first_name': 'Michael',
                'last_name': 'Davis',
                'role': 'student',
                'major_count': 1,
                'minor_count': 2,
            },
            {
                'username': 'student4',
                'email': 'student4@bc.edu',
                'first_name': 'Sarah',
                'last_name': 'Wilson',
                'role': 'student',
                'major_count': 1,
                'minor_count': 0,
            },
            {
                'username': 'student5',
                'email': 'student5@bc.edu',
                'first_name': 'David',
                'last_name': 'Martinez',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student6',
                'email': 'student6@bc.edu',
                'first_name': 'Jessica',
                'last_name': 'Anderson',
                'role': 'student',
                'major_count': 2,
                'minor_count': 0,
            },
            {
                'username': 'student7',
                'email': 'student7@bc.edu',
                'first_name': 'Christopher',
                'last_name': 'Lee',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student8',
                'email': 'student8@bc.edu',
                'first_name': 'Ashley',
                'last_name': 'Garcia',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student9',
                'email': 'student9@bc.edu',
                'first_name': 'Matthew',
                'last_name': 'Rodriguez',
                'role': 'student',
                'major_count': 2,
                'minor_count': 0,
            },
            {
                'username': 'student10',
                'email': 'student10@bc.edu',
                'first_name': 'Amanda',
                'last_name': 'White',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student11',
                'email': 'student11@bc.edu',
                'first_name': 'Daniel',
                'last_name': 'Harris',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student12',
                'email': 'student12@bc.edu',
                'first_name': 'Rachel',
                'last_name': 'Miller',
                'role': 'student',
                'major_count': 2,
                'minor_count': 0,
            },
            {
                'username': 'student13',
                'email': 'student13@bc.edu',
                'first_name': 'Kevin',
                'last_name': 'Gonzalez',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
            {
                'username': 'student14',
                'email': 'student14@bc.edu',
                'first_name': 'Lisa',
                'last_name': 'Clark',
                'role': 'student',
                'major_count': 1,
                'minor_count': 1,
            },
        ]

        # Create dummy staff
        staff = [
            {
                'username': 'staff1',
                'email': 'staff1@bc.edu',
                'first_name': 'Robert',
                'last_name': 'Brown',
                'role': 'staff',
            },
            {
                'username': 'staff2',
                'email': 'staff2@bc.edu',
                'first_name': 'Jennifer',
                'last_name': 'Taylor',
                'role': 'staff',
            },
            {
                'username': 'staff3',
                'email': 'staff3@bc.edu',
                'first_name': 'William',
                'last_name': 'Moore',
                'role': 'staff',
            },
            {
                'username': 'staff4',
                'email': 'staff4@bc.edu',
                'first_name': 'Patricia',
                'last_name': 'Jackson',
                'role': 'staff',
            },
            {
                'username': 'staff5',
                'email': 'staff5@bc.edu',
                'first_name': 'Thomas',
                'last_name': 'Thompson',
                'role': 'staff',
            },
            {
                'username': 'staff6',
                'email': 'staff6@bc.edu',
                'first_name': 'Elizabeth',
                'last_name': 'Lewis',
                'role': 'staff',
            },
            {
                'username': 'staff7',
                'email': 'staff7@bc.edu',
                'first_name': 'Richard',
                'last_name': 'Walker',
                'role': 'staff',
            },
            {
                'username': 'staff8',
                'email': 'staff8@bc.edu',
                'first_name': 'Linda',
                'last_name': 'Hall',
                'role': 'staff',
            },
            {
                'username': 'staff9',
                'email': 'staff9@bc.edu',
                'first_name': 'James',
                'last_name': 'Allen',
                'role': 'staff',
            },
            {
                'username': 'staff10',
                'email': 'staff10@bc.edu',
                'first_name': 'Susan',
                'last_name': 'Young',
                'role': 'staff',
            },
            {
                'username': 'staff11',
                'email': 'staff11@bc.edu',
                'first_name': 'Joseph',
                'last_name': 'King',
                'role': 'staff',
            },
            {
                'username': 'staff12',
                'email': 'staff12@bc.edu',
                'first_name': 'Karen',
                'last_name': 'Wright',
                'role': 'staff',
            },
        ]

        self.stdout.write('Creating dummy users...\n')
        self.majors, self.minors = self._prepare_academic_data()
        self.major_index = 0
        self.minor_index = 0

        # Create students
        for student_data in students:
            username = student_data.pop('username')
            role = student_data.pop('role')
            major_count = max(1, student_data.pop('major_count'))
            minor_count = max(0, student_data.pop('minor_count'))

            if User.objects.filter(username=username).exists():
                self.stdout.write(f'User {username} already exists, skipping...')
                continue

            user = User.objects.create_user(username=username, **student_data)
            profile = Profile.objects.get(user=user)
            profile.role = role
            self._assign_academics(profile, major_count, minor_count)
            profile.save()

            self.stdout.write(self.style.SUCCESS(f'✓ Created {role}: {username} ({user.first_name} {user.last_name})'))

        # Create staff
        for staff_data in staff:
            username = staff_data.pop('username')
            role = staff_data.pop('role')

            if User.objects.filter(username=username).exists():
                self.stdout.write(f'User {username} already exists, skipping...')
                continue

            user = User.objects.create_user(username=username, **staff_data)
            profile = Profile.objects.get(user=user)
            profile.role = role
            profile.save()

            self.stdout.write(self.style.SUCCESS(f'✓ Created {role}: {username} ({user.first_name} {user.last_name})'))

        self.stdout.write(self.style.SUCCESS('\nAll dummy users created successfully!'))
        self.stdout.write('\nLogin credentials:')
        self.stdout.write('Students: student1-student14 (password: testpass123)')
        self.stdout.write('Staff: staff1-staff12 (password: testpass123)')
        self.stdout.write('\nNote: These users do not have real BC.edu accounts, so OAuth will not work.')
        self.stdout.write('You can still test by logging in directly through Django admin if needed.')

    def _assign_academics(self, profile, major_count, minor_count):
        if not self.majors:
            raise CommandError('No majors available to assign. Please run the import_data command or ensure pct/script files exist.')

        profile.major1 = self._next_major()
        if not profile.major1:
            raise CommandError('Unable to assign a primary major from script data.')
        profile.major2 = self._next_major(exclude=[profile.major1]) if major_count > 1 else None

        if minor_count > 0 and self.minors:
            profile.minor1 = self._next_minor()
            profile.minor2 = self._next_minor(exclude=[profile.minor1]) if minor_count > 1 and len(self.minors) > 1 else None
        else:
            profile.minor1 = None
            profile.minor2 = None

    def _prepare_academic_data(self):
        script_dir = Path(settings.BASE_DIR) / 'pct' / 'script'
        majors_path = script_dir / 'schools_and_majors.csv'
        minors_path = script_dir / 'minors.csv'

        majors = self._load_majors(majors_path)
        minors = self._load_minors(minors_path)

        if not majors:
            raise CommandError(f'No majors were loaded from {majors_path}.')

        school_count = len({major.school_id for major in majors if major.school_id})
        self.stdout.write(
            f'Loaded {len(majors)} majors across {school_count} schools and {len(minors)} minors from pct/script data.\n'
        )

        if not minors:
            self.stdout.write(self.style.WARNING('Minor data was empty; students will be created without minors.\n'))

        return majors, minors

    def _load_majors(self, path: Path):
        if not path.exists():
            raise CommandError(f'Majors CSV not found at {path}.')

        majors = []
        seen = set()
        with path.open(newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                school_name = row.get('school_name', '').strip()
                major_name = row.get('major_name', '').strip()
                if not school_name or not major_name:
                    continue

                school, _ = School.objects.get_or_create(school_name=school_name)
                major, _ = Major.objects.get_or_create(major_name=major_name, school=school)
                key = (major_name.lower(), school_name.lower())
                if key not in seen:
                    majors.append(major)
                    seen.add(key)
        return majors

    def _load_minors(self, path: Path):
        if not path.exists():
            self.stdout.write(self.style.WARNING(f'Minors CSV not found at {path}; skipping minor assignment.'))
            return []

        minors = []
        seen = set()
        with path.open(newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                minor_name = row.get('minor_name', '').strip()
                if not minor_name:
                    continue
                key = minor_name.lower()
                if key in seen:
                    continue

                minor, _ = Minor.objects.get_or_create(minor_name=minor_name)
                minors.append(minor)
                seen.add(key)
        return minors

    def _next_major(self, exclude=None):
        exclude_ids = {obj.pk for obj in (exclude or []) if obj}
        for _ in range(len(self.majors)):
            major = self.majors[self.major_index]
            self.major_index = (self.major_index + 1) % len(self.majors)
            if major.pk not in exclude_ids:
                return major
        return None

    def _next_minor(self, exclude=None):
        if not self.minors:
            return None

        exclude_ids = {obj.pk for obj in (exclude or []) if obj}
        for _ in range(len(self.minors)):
            minor = self.minors[self.minor_index]
            self.minor_index = (self.minor_index + 1) % len(self.minors)
            if minor.pk not in exclude_ids:
                return minor
        return None
