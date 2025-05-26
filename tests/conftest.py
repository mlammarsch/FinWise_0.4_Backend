import pytest
import sys
import os

# Add the project root to sys.path to allow imports from 'app'
# Assumes conftest.py is in FinWise_0.4_BE/tests/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import os
import uuid

from main import app
from app.db.database import get_db as get_main_db
from app.db.tenant_db import Base as TenantBase, TENANT_DB_DIR, TENANT_DB_PREFIX, init_tenant_db, delete_tenant_db_file
from app.models.user_tenant_models import Base as UserTenantBase

DATABASE_URL_USER_TEST = "sqlite:///:memory:"

engine_user_test = create_engine(
    DATABASE_URL_USER_TEST,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocalUser = sessionmaker(autocommit=False, autoflush=False, bind=engine_user_test)

# Tenant Database Setup
# We will create unique in-memory dbs for tenants during tests or use temp files
# For simplicity in this conftest, we'll focus on the main DB override
# and tenant DBs will be handled more dynamically in specific tests or fixtures if needed.

@pytest.fixture(scope="session", autouse=True)
def create_test_databases():
    UserTenantBase.metadata.create_all(bind=engine_user_test)
    # Ensure tenant DB directory exists if we were to create file-based tenant DBs
    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR)
    yield
    # Teardown: Base.metadata.drop_all(bind=engine_user_test) # Optional: if you want to clear tables after all tests
    # Cleanup tenant DB files if any were created (more complex, handle in specific tests or fixtures)


@pytest.fixture(scope="function")
def db_session_user() -> Session:
    """Fixture for a user database session."""
    connection = engine_user_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocalUser(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session_user: Session):
    """Fixture for the FastAPI TestClient."""

    def override_get_main_db():
        try:
            yield db_session_user
        finally:
            db_session_user.close()

    app.dependency_overrides[get_main_db] = override_get_main_db

    # For tenant DBs, a more sophisticated override might be needed if tests
    # directly call get_tenant_db. For now, we assume CRUD operations for tenants
    # will correctly use their passed session or create new connections as needed.
    # If get_tenant_db is used by endpoints, it would need a similar override.

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# Fixture for creating a temporary tenant DB for testing tenant-specific operations
@pytest.fixture(scope="function")
def temp_tenant_db_session():
    """
    Creates a temporary, in-memory SQLite database session for a single tenant.
    Yields the session and the tenant_uuid.
    Cleans up by dropping all tables after the test.
    """
    tenant_uuid = str(uuid.uuid4())
    DATABASE_URL_TENANT_TEST = f"sqlite:///:memory:?uri=true&database=tenant_{tenant_uuid}" # Unique in-memory DB

    engine_tenant_test = create_engine(
        DATABASE_URL_TENANT_TEST,
        connect_args={"check_same_thread": False}, # Required for SQLite in-memory
        poolclass=StaticPool, # Recommended for SQLite in tests
    )
    TenantBase.metadata.create_all(bind=engine_tenant_test)
    TestingSessionLocalTenant = sessionmaker(autocommit=False, autoflush=False, bind=engine_tenant_test)

    connection = engine_tenant_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocalTenant(bind=connection)

    yield session, tenant_uuid

    session.close()
    transaction.rollback()
    connection.close()
    TenantBase.metadata.drop_all(bind=engine_tenant_test) # Clean up tables

@pytest.fixture(scope="function")
def temp_tenant_db_file_session():
    """
    Creates a temporary, file-based SQLite database for a single tenant.
    Yields the session, tenant_uuid, and the database file path.
    Cleans up by dropping all tables and deleting the file after the test.
    """
    tenant_uuid = str(uuid.uuid4())
    db_filename = f"{TENANT_DB_PREFIX}{tenant_uuid}.db"
    db_filepath = os.path.join(TENANT_DB_DIR, db_filename)

    # Ensure TENANT_DB_DIR exists
    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR)

    DATABASE_URL_TENANT_TEST = f"sqlite:///{db_filepath}"

    engine_tenant_test = create_engine(
        DATABASE_URL_TENANT_TEST,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TenantBase.metadata.create_all(bind=engine_tenant_test)
    TestingSessionLocalTenant = sessionmaker(autocommit=False, autoflush=False, bind=engine_tenant_test)

    connection = engine_tenant_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocalTenant(bind=connection)

    yield session, tenant_uuid, db_filepath

    session.close()
    transaction.rollback()
    connection.close()
    TenantBase.metadata.drop_all(bind=engine_tenant_test)
    if os.path.exists(db_filepath):
        os.remove(db_filepath)
