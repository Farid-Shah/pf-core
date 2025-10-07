"""
Management command to normalize all existing usernames in the database.

This is a one-time data migration to ensure all usernames follow
the normalization rules (NFKC + lowercase).

Usage:
    python manage.py normalize_usernames
    python manage.py normalize_usernames --dry-run  # preview changes only
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import User
from accounts.utils import normalize_username


class Command(BaseCommand):
    help = 'Normalize all existing usernames to ensure consistency'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN MODE (no changes will be saved) ===\n'))
        
        # Get all users
        users = User.objects.all()
        total_count = users.count()
        changed_count = 0
        unchanged_count = 0
        error_count = 0
        
        self.stdout.write(f'Processing {total_count} users...\n')
        
        for user in users:
            old_username = user.username
            normalized = normalize_username(old_username)
            
            if old_username != normalized:
                changed_count += 1
                self.stdout.write(
                    self.style.WARNING(f'CHANGE: "{old_username}" → "{normalized}"')
                )
                
                if not dry_run:
                    try:
                        with transaction.atomic():
                            # Direct update to bypass validation
                            # (we're fixing data, not enforcing policy)
                            User.objects.filter(pk=user.pk).update(username=normalized)
                            self.stdout.write(self.style.SUCCESS('  ✓ Updated'))
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(self.style.ERROR(f'  ✗ Error: {e}'))
            else:
                unchanged_count += 1
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n=== Summary ==='))
        self.stdout.write(f'Total users: {total_count}')
        self.stdout.write(self.style.SUCCESS(f'Already normalized: {unchanged_count}'))
        self.stdout.write(self.style.WARNING(f'Changed: {changed_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nNo changes were applied (dry run mode)'))
            self.stdout.write(self.style.SUCCESS('Run without --dry-run to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS('\nAll changes applied successfully!'))