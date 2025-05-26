from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest
import os
import shutil # For cleaning up tenant DB files if created

from app.models.schemas import TenantCreate, Tenant
from app.models.schemas import UserCreate
from app.db import crud
from app.db.tenant_db import TENANT_DB_DIR, TENANT_DB_PREFIX

API_V1_STR = "/api/v1"

def create_user_for_tenant_tests(client: TestClient, email: str = "tenantuser@example.com", name: str = "Tenant User") -> int:
    user_data = {"email": email, "password": "password123", "name": name}
    response = client.post(f"{API_V1_STR}/users/", json=user_data)
    assert response.status_code == 200
    return response.json()["id"]

def test_create_tenant_success(client: TestClient, db_session_user: Session):
    """Test successful tenant creation."""
    user_id = create_user_for_tenant_tests(client, "tenantowner1@example.com", "Tenant Owner 1")
    tenant_data = {"name": "My First Tenant", "user_id": user_id}

    response = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    assert response.status_code == 200
    created_tenant = response.json()
    assert created_tenant["name"] == tenant_data["name"]
    assert created_tenant["user_id"] == user_id
    assert "id" in created_tenant
    assert "db_name" in created_tenant

    db_tenant = crud.get_tenant(db_session_user, tenant_id=created_tenant["id"])
    assert db_tenant is not None
    assert db_tenant.name == tenant_data["name"]
    assert db_tenant.user_id == user_id
    assert db_tenant.db_name.startswith(TENANT_DB_PREFIX)

    tenant_db_path = os.path.join(TENANT_DB_DIR, db_tenant.db_name)
    assert os.path.exists(tenant_db_path)

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)


def test_create_tenant_invalid_user_id(client: TestClient):
    """Test error when creating a tenant with an invalid user_id."""
    non_existent_user_id = 99999
    tenant_data = {"name": "Tenant With Invalid User", "user_id": non_existent_user_id}
    response = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    assert response.status_code == 404
    error_detail = response.json()
    assert "User with id" in error_detail["detail"] and "not found" in error_detail["detail"]

def test_create_tenant_duplicate_name_for_user(client: TestClient, db_session_user: Session):
    """Test error when creating a tenant with a duplicate name for the same user."""
    user_id = create_user_for_tenant_tests(client, "tenantowner2@example.com", "Tenant Owner 2")
    tenant_data = {"name": "Duplicate Tenant Name", "user_id": user_id}

    response1 = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    assert response1.status_code == 200
    tenant_id1 = response1.json()["id"]
    db_tenant1 = crud.get_tenant(db_session_user, tenant_id=tenant_id1)
    tenant_db_path1 = os.path.join(TENANT_DB_DIR, db_tenant1.db_name)

    response2 = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    assert response2.status_code == 400
    error_detail = response2.json()
    assert "Tenant with name" in error_detail["detail"] and "already exists for this user" in error_detail["detail"]

    if os.path.exists(tenant_db_path1):
        os.remove(tenant_db_path1)


def test_get_tenants_empty(client: TestClient):
    """Test getting an empty list of tenants."""
    response = client.get(f"{API_V1_STR}/tenants/")
    assert response.status_code == 200
    assert response.json() == []

def test_get_tenants_multiple_and_filter_by_user_id(client: TestClient, db_session_user: Session):
    """Test getting multiple tenants and filtering by user_id."""
    user_id1 = create_user_for_tenant_tests(client, "tenantowner3@example.com", "Tenant Owner 3")
    user_id2 = create_user_for_tenant_tests(client, "tenantowner4@example.com", "Tenant Owner 4")

    tenant_data1_user1 = {"name": "Tenant1 User1", "user_id": user_id1}
    tenant_data2_user1 = {"name": "Tenant2 User1", "user_id": user_id1}
    tenant_data1_user2 = {"name": "Tenant1 User2", "user_id": user_id2}

    res1 = client.post(f"{API_V1_STR}/tenants/", json=tenant_data1_user1)
    res2 = client.post(f"{API_V1_STR}/tenants/", json=tenant_data2_user1)
    res3 = client.post(f"{API_V1_STR}/tenants/", json=tenant_data1_user2)

    db_tenant1 = crud.get_tenant(db_session_user, tenant_id=res1.json()["id"])
    db_tenant2 = crud.get_tenant(db_session_user, tenant_id=res2.json()["id"])
    db_tenant3 = crud.get_tenant(db_session_user, tenant_id=res3.json()["id"])

    paths_to_clean = [
        os.path.join(TENANT_DB_DIR, db_tenant1.db_name),
        os.path.join(TENANT_DB_DIR, db_tenant2.db_name),
        os.path.join(TENANT_DB_DIR, db_tenant3.db_name)
    ]

    response_all = client.get(f"{API_V1_STR}/tenants/")
    assert response_all.status_code == 200
    tenants_list_all = response_all.json()
    assert len(tenants_list_all) == 3

    response_user1 = client.get(f"{API_V1_STR}/tenants/?user_id={user_id1}")
    assert response_user1.status_code == 200
    tenants_list_user1 = response_user1.json()
    assert len(tenants_list_user1) == 2
    for tenant in tenants_list_user1:
        assert tenant["user_id"] == user_id1
    names_user1 = [t["name"] for t in tenants_list_user1]
    assert tenant_data1_user1["name"] in names_user1
    assert tenant_data2_user1["name"] in names_user1

    response_user2 = client.get(f"{API_V1_STR}/tenants/?user_id={user_id2}")
    assert response_user2.status_code == 200
    tenants_list_user2 = response_user2.json()
    assert len(tenants_list_user2) == 1
    assert tenants_list_user2[0]["user_id"] == user_id2
    assert tenants_list_user2[0]["name"] == tenant_data1_user2["name"]

    for p in paths_to_clean:
        if os.path.exists(p):
            os.remove(p)


def test_get_tenant_by_id_found(client: TestClient, db_session_user: Session):
    """Test getting a tenant by ID when the tenant exists."""
    user_id = create_user_for_tenant_tests(client, "tenantowner5@example.com", "Tenant Owner 5")
    tenant_data = {"name": "GetMe Tenant", "user_id": user_id}
    create_response = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    created_tenant_id = create_response.json()["id"]
    db_tenant = crud.get_tenant(db_session_user, tenant_id=created_tenant_id)
    tenant_db_path = os.path.join(TENANT_DB_DIR, db_tenant.db_name)

    response = client.get(f"{API_V1_STR}/tenants/{created_tenant_id}")
    assert response.status_code == 200
    retrieved_tenant = response.json()
    assert retrieved_tenant["id"] == created_tenant_id
    assert retrieved_tenant["name"] == tenant_data["name"]
    assert retrieved_tenant["user_id"] == user_id

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)

def test_get_tenant_by_id_not_found(client: TestClient):
    """Test getting a tenant by ID when the tenant does not exist (404)."""
    non_existent_tenant_id = 99999
    response = client.get(f"{API_V1_STR}/tenants/{non_existent_tenant_id}")
    assert response.status_code == 404
    error_detail = response.json()
    assert "Tenant not found" in error_detail["detail"]

def test_delete_tenant_success(client: TestClient, db_session_user: Session):
    """Test successful tenant deletion, including the tenant DB file."""
    user_id = create_user_for_tenant_tests(client, "tenantowner6@example.com", "Tenant Owner 6")
    tenant_data = {"name": "DeleteMe Tenant", "user_id": user_id}
    create_response = client.post(f"{API_V1_STR}/tenants/", json=tenant_data)
    assert create_response.status_code == 200
    created_tenant = create_response.json()
    tenant_id_to_delete = created_tenant["id"]

    db_tenant_before_delete = crud.get_tenant(db_session_user, tenant_id=tenant_id_to_delete)
    assert db_tenant_before_delete is not None
    tenant_db_filename = db_tenant_before_delete.db_name
    tenant_db_path = os.path.join(TENANT_DB_DIR, tenant_db_filename)

    assert os.path.exists(tenant_db_path), f"Tenant DB file {tenant_db_path} should exist before deletion."

    delete_response = client.delete(f"{API_V1_STR}/tenants/{tenant_id_to_delete}")
    assert delete_response.status_code == 200
    deleted_tenant_details = delete_response.json()
    assert deleted_tenant_details["name"] == tenant_data["name"]
    assert deleted_tenant_details["id"] == tenant_id_to_delete

    assert crud.get_tenant(db_session_user, tenant_id=tenant_id_to_delete) is None

    assert not os.path.exists(tenant_db_path), f"Tenant DB file {tenant_db_path} should be deleted."

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)


def test_delete_tenant_not_found(client: TestClient):
    """Test deleting a tenant that does not exist (404)."""
    non_existent_tenant_id = 88888
    response = client.delete(f"{API_V1_STR}/tenants/{non_existent_tenant_id}")
    assert response.status_code == 404
    error_detail = response.json()
    assert "Tenant not found" in error_detail["detail"]

@pytest.fixture(scope="session", autouse=True)
def cleanup_tenant_db_dir_after_tests():
    """Ensures the base tenant DB directory is cleaned up if empty after tests."""
    yield
    if os.path.exists(TENANT_DB_DIR):
        try:
            if not os.listdir(TENANT_DB_DIR):
                shutil.rmtree(TENANT_DB_DIR)
        except OSError as e:
            print(f"Error cleaning up {TENANT_DB_DIR}: {e}")
            pass
