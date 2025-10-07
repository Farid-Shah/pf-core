"""
Tests for groups app.

Test structure:
- test_models.py: Model tests (properties, methods, validation)
- test_services.py: Service layer tests (business logic)
- test_permissions.py: Permission system tests (13 permissions)
- test_api.py: API endpoint tests (13 endpoints)
- test_integration.py: Integration tests (complete workflows)

Run all tests:
    python manage.py test groups

Run specific test file:
    python manage.py test groups.tests.test_models

Run specific test class:
    python manage.py test groups.tests.test_models.GroupModelTests

Run specific test method:
    python manage.py test groups.tests.test_models.GroupModelTests.test_group_creation

Run with coverage:
    coverage run --source='groups' manage.py test groups
    coverage report
    coverage html
"""