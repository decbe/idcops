import os

import django

# Configure Django settings before importing any Django modules
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idcops.settings")

django.setup()


import pytest


@pytest.fixture(scope="session")
def django_db_setup():
    """Set up the test database."""
    pass


@pytest.fixture
def api_client():
    """Provide a test API client."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def authenticated_client(api_client, test_user):
    """Provide an authenticated test client."""
    api_client.force_authenticate(user=test_user)
    return api_client


@pytest.fixture
def test_user(db):
    """Create a test user."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="testuser",
        defaults={"is_active": True},
    )
    user.set_password("testpass123")
    user.save()
    return user
