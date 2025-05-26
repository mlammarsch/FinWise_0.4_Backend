import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
import os
import uuid
import shutil

from app.db.database import Base as MainBase, engine as main_engine, SessionLocal as MainSessionLocal, create_db_and_tables as create_main_db_and_tables
from app.db.tenant_db import Base as TenantBase, TENANT_DB_DIR, TENANT_DB_PREFIX, init_tenant_db, get_tenant_db_url, create_tenant_db_engine, create_tenant_db_session_local, delete_tenant_db_file
from app.models.user_tenant_models import User, Tenant
from app.config import SQLALCHEMY_DATABASE_URL

def test_main_database_connection_and_table_creation():
    """
    Tests the main database engine connection and table creation.
    Uses the test engine configured in conftest.py.
    """
    from ..conftest import engine_user_test

    inspector = inspect(engine_user_test)
    table_names = inspector.get_table_names()

    assert User.__tablename__ in table_names
    assert Tenant.__tablename__ in table_names

# We don't call create_main_db_and_tables() directly here as it uses the production engine.
# The test setup in conftest.py handles creating tables on the test database.
# If we wanted to test create_main_db_and_tables specifically, we'd need to mock its engine.


def test_get_tenant_db_url():
    """Test the generation of tenant DB URLs."""
    tenant_uuid = str(uuid.uuid4())
    expected_filename = f"{TENANT_DB_PREFIX}{tenant_uuid}.db"
    expected_path = os.path.join(TENANT_DB_DIR, expected_filename)

    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR, exist_ok=True)

    db_url = get_tenant_db_url(tenant_uuid)

    assert expected_filename in db_url
    assert db_url.startswith("sqlite:///")

    if os.path.exists(TENANT_DB_DIR) and not os.listdir(TENANT_DB_DIR):
        os.rmdir(TENANT_DB_DIR)
    elif os.path.exists(expected_path):
        os.remove(expected_path)


def test_create_tenant_db(temp_tenant_db_file_session):
    """
    Test the creation of a tenant-specific database file and its tables.
    Uses the temp_tenant_db_file_session fixture from conftest.py which handles creation and cleanup.
    This fixture effectively calls create_tenant_db indirectly by setting up a file-based tenant DB.
    """
    _, tenant_uuid, db_filepath = temp_tenant_db_file_session

    assert os.path.exists(db_filepath)

    inspector = inspect(create_engine(f"sqlite:///{db_filepath}"))
    table_names = inspector.get_table_names()

    # Check for expected tables in a tenant DB (defined with TenantBase)
    # If TenantBase has tables, check for them here.


def test_create_tenant_db_direct_call():
    """Test create_tenant_db function directly."""
    tenant_uuid = str(uuid.uuid4())
    db_filepath = os.path.join(TENANT_DB_DIR, f"{TENANT_DB_PREFIX}{tenant_uuid}.db")

    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR, exist_ok=True)

    if os.path.exists(db_filepath):
        os.remove(db_filepath)

    try:
        created_engine = init_tenant_db(tenant_uuid)
        assert created_engine is not None
        assert os.path.exists(db_filepath)

        inspector = inspect(created_engine)
        # Add assertions for expected tables based on TenantBase as in the previous test

    finally:
        if os.path.exists(db_filepath):
            os.remove(db_filepath)
        if os.path.exists(TENANT_DB_DIR) and not os.listdir(TENANT_DB_DIR):
            try:
                os.rmdir(TENANT_DB_DIR)
            except OSError:
                pass


def test_delete_tenant_db_file():
    """Test the deletion of a tenant-specific database file."""
    tenant_uuid = str(uuid.uuid4())
    db_filename = f"{TENANT_DB_PREFIX}{tenant_uuid}.db"
    db_filepath = os.path.join(TENANT_DB_DIR, db_filename)

    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR, exist_ok=True)

    with open(db_filepath, "w") as f:
        f.write("test")

    assert os.path.exists(db_filepath)

    delete_tenant_db_file(tenant_uuid)

    assert not os.path.exists(db_filepath)

    if os.path.exists(TENANT_DB_DIR) and not os.listdir(TENANT_DB_DIR):
        try:
            os.rmdir(TENANT_DB_DIR)
        except OSError:
            pass


def test_get_tenant_engine_and_session():
    """Test getting a tenant-specific engine and session local."""
    tenant_uuid = str(uuid.uuid4())
    db_filepath = os.path.join(TENANT_DB_DIR, f"{TENANT_DB_PREFIX}{tenant_uuid}.db")

    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR, exist_ok=True)

    engine = init_tenant_db(tenant_uuid)
    assert os.path.exists(db_filepath)

    try:
        retrieved_engine = create_tenant_db_engine(tenant_uuid)
        assert retrieved_engine is not None
        assert str(retrieved_engine.url) == str(engine.url)

        SessionLocalTenant = create_tenant_db_session_local(tenant_uuid)
        assert SessionLocalTenant is not None

        db: Session = SessionLocalTenant()
        assert db is not None
        db.close()

    finally:
        if os.path.exists(db_filepath):
            os.remove(db_filepath)
        if os.path.exists(TENANT_DB_DIR) and not os.listdir(TENANT_DB_DIR):
            try:
                os.rmdir(TENANT_DB_DIR)
            except OSError:
                pass

# Fixture to clean up TENANT_DB_DIR if it's empty after all tests in this module
@pytest.fixture(scope="module", autouse=True)
def cleanup_tenant_db_dir_module():
    yield
    if os.path.exists(TENANT_DB_DIR):
        try:
            if not os.listdir(TENANT_DB_DIR): # Check if directory is empty
                shutil.rmtree(TENANT_DB_DIR)
        except OSError:
            # print(f"Notice: {TENANT_DB_DIR} was not empty after module tests or couldn't be removed.")
            pass
