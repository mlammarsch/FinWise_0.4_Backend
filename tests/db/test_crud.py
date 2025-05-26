import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import os
import uuid

from app.db import crud
from app.models.schemas import UserCreate
from app.models.schemas import TenantCreate
from app.models.user_tenant_models import User, Tenant
from app.db.tenant_db import TENANT_DB_DIR, TENANT_DB_PREFIX, init_tenant_db, delete_tenant_db_file
from app.db.crud import get_password_hash

def test_create_user(db_session_user: Session):
    """Test creating a new user."""
    user_in = UserCreate(email="testcrud@example.com", password="password123", name="Test User Crud")
    db_user = crud.create_user(db_session_user, user=user_in)

    assert db_user is not None
    assert db_user.email == user_in.email
    assert db_user.id is not None
    assert db_user.hashed_password is not None
    assert db_user.hashed_password != user_in.password


def test_create_user_duplicate_email_crud(db_session_user: Session):
    """Test creating a user with a duplicate email directly via CRUD should raise IntegrityError."""
    user_in1 = UserCreate(email="duplicatecrud@example.com", password="password123", name="Duplicate User 1")
    crud.create_user(db_session_user, user=user_in1)

    user_in2 = UserCreate(email="duplicatecrud@example.com", password="password456", name="Duplicate User 2")
    with pytest.raises(IntegrityError): # SQLAlchemy raises IntegrityError for unique constraint violations
        crud.create_user(db_session_user, user=user_in2)
        db_session_user.commit() # commit is needed to trigger the constraint check if not autoflushed


def test_get_user(db_session_user: Session):
    """Test retrieving a user by ID."""
    user_in = UserCreate(email="getme_crud@example.com", password="password123", name="Get Me User")
    created_user = crud.create_user(db_session_user, user=user_in)

    retrieved_user = crud.get_user(db_session_user, user_id=created_user.id)
    assert retrieved_user is not None
    assert retrieved_user.id == created_user.id
    assert retrieved_user.email == created_user.email

def test_get_user_non_existent(db_session_user: Session):
    """Test retrieving a non-existent user by ID returns None."""
    retrieved_user = crud.get_user(db_session_user, user_id=99999)
    assert retrieved_user is None

def test_get_user_by_email(db_session_user: Session):
    """Test retrieving a user by email."""
    user_in = UserCreate(email="getmebyemail@example.com", password="password123", name="Get Me By Email")
    crud.create_user(db_session_user, user=user_in)

    retrieved_user = crud.get_user_by_email(db_session_user, email=user_in.email)
    assert retrieved_user is not None
    assert retrieved_user.email == user_in.email

def test_get_user_by_email_non_existent(db_session_user: Session):
    """Test retrieving a non-existent user by email returns None."""
    retrieved_user = crud.get_user_by_email(db_session_user, email="noexist@example.com")
    assert retrieved_user is None

def test_get_users(db_session_user: Session):
    """Test retrieving multiple users with skip and limit."""
    crud.create_user(db_session_user, user=UserCreate(email="user1_crud@example.com", password="p1", name="User 1"))
    crud.create_user(db_session_user, user=UserCreate(email="user2_crud@example.com", password="p2", name="User 2"))
    crud.create_user(db_session_user, user=UserCreate(email="user3_crud@example.com", password="p3", name="User 3"))

    users_all = crud.get_users(db_session_user, skip=0, limit=10)
    assert len(users_all) == 3

    users_limited = crud.get_users(db_session_user, skip=1, limit=1)
    assert len(users_limited) == 1
    assert users_limited[0].email == "user2_crud@example.com" # Assumes ordering by ID or insertion

    users_skip_all = crud.get_users(db_session_user, skip=3, limit=10)
    assert len(users_skip_all) == 0


# Tenant CRUD tests
def test_create_tenant(db_session_user: Session):
    """Test creating a new tenant."""
    user_in = UserCreate(email="tenantowner_crud@example.com", password="password123", name="Tenant Owner Crud")
    db_user = crud.create_user(db_session_user, user=user_in)

    tenant_in = TenantCreate(name="MyCrudTenant", user_id=db_user.id)
    db_tenant = crud.create_tenant(db_session_user, tenant=tenant_in)

    assert db_tenant is not None
    assert db_tenant.name == tenant_in.name
    assert db_tenant.user_id == db_user.id
    assert db_tenant.id is not None
    assert db_tenant.db_name is not None
    assert db_tenant.db_name.startswith(TENANT_DB_PREFIX)

    tenant_db_path = os.path.join(TENANT_DB_DIR, db_tenant.db_name)
    assert os.path.exists(tenant_db_path)

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)

def test_create_tenant_duplicate_name_for_user_crud(db_session_user: Session):
    """Test creating a tenant with a duplicate name for the same user directly via CRUD."""
    user_in = UserCreate(email="tenantowner_dup_crud@example.com", password="password123", name="Tenant Owner Dup")
    db_user = crud.create_user(db_session_user, user=user_in)

    tenant_in1 = TenantCreate(name="DuplicateNameTenant", user_id=db_user.id)
    db_tenant1 = crud.create_tenant(db_session_user, tenant=tenant_in1)
    tenant_db_path1 = os.path.join(TENANT_DB_DIR, db_tenant1.db_name)

    tenant_in2 = TenantCreate(name="DuplicateNameTenant", user_id=db_user.id)
    # This should not raise an IntegrityError at the DB level for the tenants table itself
    # if the (user_id, name) unique constraint is not there or handled in business logic.
    # The current crud.create_tenant checks this before insertion.
    # If the check in crud.create_tenant is removed, and a DB constraint (user_id, name) exists,
    # then it would raise IntegrityError.
    # Let's assume the check in crud.create_tenant is the primary guard.
    # The current implementation of crud.create_tenant returns the existing tenant if found.

    existing_tenant_or_new = crud.create_tenant(db_session_user, tenant=tenant_in2)
    assert existing_tenant_or_new is not None
    assert existing_tenant_or_new.id == db_tenant1.id # Should return the existing one
    assert existing_tenant_or_new.name == tenant_in1.name

    # Ensure no new DB file was created for the "duplicate"
    # This requires checking how many files match the pattern for this user if multiple tenants are allowed
    # For this specific test, we just ensure the original one is still there.
    assert os.path.exists(tenant_db_path1)

    if os.path.exists(tenant_db_path1):
        os.remove(tenant_db_path1)


def test_get_tenant(db_session_user: Session):
    """Test retrieving a tenant by ID."""
    user_in = UserCreate(email="owner_for_get_tenant@example.com", password="pw", name="Owner Get Tenant")
    db_user = crud.create_user(db_session_user, user=user_in)
    tenant_in = TenantCreate(name="GetThisTenant", user_id=db_user.id)
    created_tenant = crud.create_tenant(db_session_user, tenant=tenant_in)
    tenant_db_path = os.path.join(TENANT_DB_DIR, created_tenant.db_name)

    retrieved_tenant = crud.get_tenant(db_session_user, tenant_id=created_tenant.id)
    assert retrieved_tenant is not None
    assert retrieved_tenant.id == created_tenant.id
    assert retrieved_tenant.name == created_tenant.name

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)

def test_get_tenant_non_existent(db_session_user: Session):
    """Test retrieving a non-existent tenant by ID returns None."""
    retrieved_tenant = crud.get_tenant(db_session_user, tenant_id=99999)
    assert retrieved_tenant is None

def test_get_tenants_by_user(db_session_user: Session):
    """Test retrieving tenants for a specific user."""
    user1_in = UserCreate(email="user1_tenants@example.com", password="pw", name="User 1 Tenants")
    db_user1 = crud.create_user(db_session_user, user=user1_in)
    user2_in = UserCreate(email="user2_tenants@example.com", password="pw", name="User 2 Tenants")
    db_user2 = crud.create_user(db_session_user, user=user2_in)

    tenant1_u1_in = TenantCreate(name="T1U1", user_id=db_user1.id)
    tenant2_u1_in = TenantCreate(name="T2U1", user_id=db_user1.id)
    tenant1_u2_in = TenantCreate(name="T1U2", user_id=db_user2.id)

    t1u1 = crud.create_tenant(db_session_user, tenant=tenant1_u1_in)
    t2u1 = crud.create_tenant(db_session_user, tenant=tenant2_u1_in)
    t1u2 = crud.create_tenant(db_session_user, tenant=tenant1_u2_in)

    paths_to_clean = [
        os.path.join(TENANT_DB_DIR, t1u1.db_name),
        os.path.join(TENANT_DB_DIR, t2u1.db_name),
        os.path.join(TENANT_DB_DIR, t1u2.db_name)
    ]

    tenants_user1 = crud.get_tenants_by_user(db_session_user, user_id=db_user1.id)
    assert len(tenants_user1) == 2
    tenant_names_u1 = {t.name for t in tenants_user1}
    assert "T1U1" in tenant_names_u1
    assert "T2U1" in tenant_names_u1

    tenants_user2 = crud.get_tenants_by_user(db_session_user, user_id=db_user2.id)
    assert len(tenants_user2) == 1
    assert tenants_user2[0].name == "T1U2"

    for p in paths_to_clean:
        if os.path.exists(p):
            os.remove(p)


def test_get_tenants_by_user_non_existent_user(db_session_user: Session):
    """Test retrieving tenants for a non-existent user returns an empty list."""
    tenants = crud.get_tenants_by_user(db_session_user, user_id=88888)
    assert tenants == []


def test_delete_tenant(db_session_user: Session):
    """Test deleting a tenant."""
    user_in = UserCreate(email="owner_for_delete_tenant@example.com", password="pw", name="Owner Delete Tenant")
    db_user = crud.create_user(db_session_user, user=user_in)
    tenant_in = TenantCreate(name="DeleteThisTenant", user_id=db_user.id)
    created_tenant = crud.create_tenant(db_session_user, tenant=tenant_in)

    tenant_db_path = os.path.join(TENANT_DB_DIR, created_tenant.db_name)
    assert os.path.exists(tenant_db_path)

    deleted_tenant = crud.delete_tenant(db_session_user, tenant_id=created_tenant.id)
    assert deleted_tenant is not None
    assert deleted_tenant.id == created_tenant.id

    assert crud.get_tenant(db_session_user, tenant_id=created_tenant.id) is None
    assert not os.path.exists(tenant_db_path)

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)


def test_delete_tenant_non_existent(db_session_user: Session):
    """Test deleting a non-existent tenant returns None."""
    deleted_tenant = crud.delete_tenant(db_session_user, tenant_id=77777)
    assert deleted_tenant is None

def test_get_tenant_by_user_and_name(db_session_user: Session):
    """Test retrieving a tenant by user ID and tenant name."""
    user_in = UserCreate(email="owner_for_get_tenant_by_name@example.com", password="pw", name="Owner Get By Name")
    db_user = crud.create_user(db_session_user, user=user_in)

    tenant_name = "UniqueTenantNameForUser"
    tenant_in = TenantCreate(name=tenant_name, user_id=db_user.id)
    created_tenant = crud.create_tenant(db_session_user, tenant=tenant_in)
    tenant_db_path = os.path.join(TENANT_DB_DIR, created_tenant.db_name)

    retrieved_tenant = crud.get_tenant_by_user_and_name(db_session_user, user_id=db_user.id, tenant_name=tenant_name)
    assert retrieved_tenant is not None
    assert retrieved_tenant.id == created_tenant.id
    assert retrieved_tenant.name == tenant_name

    non_existent = crud.get_tenant_by_user_and_name(db_session_user, user_id=db_user.id, tenant_name="NonExistentName")
    assert non_existent is None

    non_existent_user = crud.get_tenant_by_user_and_name(db_session_user, user_id=999, tenant_name=tenant_name)
    assert non_existent_user is None

    if os.path.exists(tenant_db_path):
        os.remove(tenant_db_path)
