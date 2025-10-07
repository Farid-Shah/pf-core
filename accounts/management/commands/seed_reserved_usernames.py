"""
Management command to seed reserved usernames from settings.

Usage:
    python manage.py seed_reserved_usernames
    python manage.py seed_reserved_usernames --clear  # clear existing first
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import ReservedUsername
from accounts.utils import normalize_username


class Command(BaseCommand):
    help = 'Seed reserved usernames from settings.RESERVED_USERNAMES_DEFAULT into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing permanent reserved usernames before seeding',
        )

    def handle(self, *args, **options):
        # Get reserved usernames from settings
        reserved_set = getattr(settings, 'RESERVED_USERNAMES_DEFAULT', set())
        
        if not reserved_set:
            self.stdout.write(self.style.WARNING('No reserved usernames found in settings.RESERVED_USERNAMES_DEFAULT'))
            return
        
        # Clear existing if requested
        if options['clear']:
            count = ReservedUsername.objects.filter(
                protected=True,
                expires_at__isnull=True,
                reserved_by__isnull=True
            ).count()
            ReservedUsername.objects.filter(
                protected=True,
                expires_at__isnull=True,
                reserved_by__isnull=True
            ).delete()
            self.stdout.write(self.style.WARNING(f'Cleared {count} existing permanent reserved usernames'))
        
        # Seed from settings
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for username in reserved_set:
            normalized = normalize_username(username)
            
            # Check if already exists
            obj, created = ReservedUsername.objects.get_or_create(
                name_ci=normalized,
                defaults={
                    'name': username,
                    'protected': True,
                    'reason': 'system'
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created: {username}'))
            else:
                # Update if it's a permanent reservation
                if obj.expires_at is None and obj.reserved_by is None:
                    obj.protected = True
                    obj.reason = 'system'
                    obj.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f'↻ Updated: {username}'))
                else:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(f'⊗ Skipped (temporary reservation): {username}'))
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n=== Summary ==='))
        self.stdout.write(self.style.SUCCESS(f'Created: {created_count}'))
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        self.stdout.write(self.style.SUCCESS(f'Total in DB: {ReservedUsername.objects.filter(protected=True, expires_at__isnull=True).count()}'))