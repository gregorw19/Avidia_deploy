from django.core.management.base import BaseCommand
from pct.models import CertificationType, CertificationLevel, Certification

class Command(BaseCommand):
    help = 'Load initial certification types and levels'
    
    def handle(self, *args, **options):
        # Certification Types
        types = [
            {
                'name': '3D Printing',
                'description': 'Certification for operating 3D printers safely and effectively.'
            },
            {
                'name': 'Woodworking',
                'description': 'Certification for using woodworking tools and machinery.'
            },
            {
                'name': 'Laser Cutting',
                'description': 'Certification for operating laser cutting machines.'
            },
            {
                'name': 'Vinyl Cutting',
                'description': 'Certification for using vinyl cutting machines.'
            },
            {
                'name': 'Electronics',
                'description': 'Certification for working with electronic components and circuits.'
            },
            {
                'name': 'Metalworking',
                'description': 'Certification for using metalworking tools and machinery.'
            },
            {
                'name': 'Textiles',
                'description': 'Certification for working with textile materials and sewing machines.'
            }
        ]

        levels = [1, 2, 3]

        # Create levels, types, then complete certifications
        self.stdout.write('Creating certification levels...')
        for level in levels:
            obj, created = CertificationLevel.objects.get_or_create(level=level)
            if created:
                self.stdout.write(f'Created certification level: {level}')
            else:
                self.stdout.write(f'Certification level already exists: {level}')

        self.stdout.write('Creating certification types and certifications...')
        for cert_type in types:
            obj, created = CertificationType.objects.get_or_create(
                name=cert_type['name'],
                description=cert_type['description']
            )

            for level in levels:
                certification, created = Certification.objects.get_or_create(type=obj, level=CertificationLevel.objects.get(level=level))
                if created:
                    self.stdout.write(f'Created certification: {certification.type.name} - Level {certification.level.level}')
                else:
                    self.stdout.write(f'Certification already exists: {certification.type.name} - Level {certification.level.level}')