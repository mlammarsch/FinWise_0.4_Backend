import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import get_db
from app.models.user_tenant_models import Base as UserTenantBase
from app.config import TENANT_DATABASE_DIR
from app.db import crud
from app.models import schemas

# Test-Datenbank Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_tenant_management.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def setup_database():
    """Setup test database"""
    UserTenantBase.metadata.create_all(bind=engine)
    yield
    UserTenantBase.metadata.drop_all(bind=engine)
    # Cleanup test database file
    if os.path.exists("./test_tenant_management.db"):
        os.remove("./test_tenant_management.db")

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)

@pytest.fixture
def test_user_and_tenant(setup_database):
    """Create test user and tenant"""
    db = TestingSessionLocal()

    # Create test user
    user_data = schemas.RegisterUserPayload(
        name="Test User",
        email="test@example.com",
        password="testpassword123"
    )
    test_user = crud.create_user_with_password(db, user_data)

    # Create test tenant
    tenant_data = schemas.TenantCreate(
        name="Test Tenant",
        user_id=test_user.uuid,
        uuid="test-tenant-uuid-123"
    )
    test_tenant = crud.create_tenant(db, tenant_data)

    db.close()

    yield {
        "user": test_user,
        "tenant": test_tenant
    }

    # Cleanup
    db = TestingSessionLocal()
    try:
        # Delete tenant and user
        crud.delete_tenant(db, test_tenant.uuid)
        db.query(crud.models.User).filter(crud.models.User.uuid == test_user.uuid).delete()
        db.commit()
    except:
        db.rollback()
    finally:
        db.close()

class TestTenantManagement:
    """Test cases for tenant management API endpoints"""

    def test_delete_tenant_completely_success(self, client, test_user_and_tenant):
        """Test successful complete tenant deletion"""
        tenant = test_user_and_tenant["tenant"]
        user = test_user_and_tenant["user"]

        response = client.delete(
            f"/tenants/{tenant.uuid}/complete?user_id={user.uuid}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == tenant.uuid
        assert data["name"] == tenant.name

    def test_delete_tenant_completely_not_found(self, client, test_user_and_tenant):
        """Test tenant deletion with non-existent tenant"""
        user = test_user_and_tenant["user"]

        response = client.delete(
            f"/tenants/non-existent-tenant/complete?user_id={user.uuid}"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_tenant_completely_unauthorized(self, client, test_user_and_tenant):
        """Test tenant deletion with unauthorized user"""
        tenant = test_user_and_tenant["tenant"]

        response = client.delete(
            f"/tenants/{tenant.uuid}/complete?user_id=unauthorized-user-id"
        )

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()

    def test_reset_tenant_database_success(self, client, test_user_and_tenant):
        """Test successful tenant database reset"""
        tenant = test_user_and_tenant["tenant"]
        user = test_user_and_tenant["user"]

        response = client.post(
            f"/tenants/{tenant.uuid}/reset-database?user_id={user.uuid}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == tenant.uuid
        assert "successfully reset" in data["message"].lower()

    def test_reset_tenant_database_not_found(self, client, test_user_and_tenant):
        """Test database reset with non-existent tenant"""
        user = test_user_and_tenant["user"]

        response = client.post(
            f"/tenants/non-existent-tenant/reset-database?user_id={user.uuid}"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_reset_tenant_database_unauthorized(self, client, test_user_and_tenant):
        """Test database reset with unauthorized user"""
        tenant = test_user_and_tenant["tenant"]

        response = client.post(
            f"/tenants/{tenant.uuid}/reset-database?user_id=unauthorized-user-id"
        )

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()

    def test_clear_sync_queue_success(self, client, test_user_and_tenant):
        """Test successful sync queue clearing"""
        tenant = test_user_and_tenant["tenant"]
        user = test_user_and_tenant["user"]

        response = client.delete(
            f"/tenants/{tenant.uuid}/sync-queue?user_id={user.uuid}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == tenant.uuid
        assert "successfully cleared" in data["message"].lower()

    def test_clear_sync_queue_not_found(self, client, test_user_and_tenant):
        """Test sync queue clearing with non-existent tenant"""
        user = test_user_and_tenant["user"]

        response = client.delete(
            f"/tenants/non-existent-tenant/sync-queue?user_id={user.uuid}"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_clear_sync_queue_unauthorized(self, client, test_user_and_tenant):
        """Test sync queue clearing with unauthorized user"""
        tenant = test_user_and_tenant["tenant"]

        response = client.delete(
            f"/tenants/{tenant.uuid}/sync-queue?user_id=unauthorized-user-id"
        )

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
