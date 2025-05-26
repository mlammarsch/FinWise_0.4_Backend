from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest

from app.models.schemas import UserCreate, User
from app.db import crud

API_V1_STR = "/api/v1"

def test_create_user_success(client: TestClient, db_session_user: Session):
    """Test successful user creation."""
    user_data = {"email": "test@example.com", "password": "password123", "name": "Test User"}
    response = client.post(f"{API_V1_STR}/users/", json=user_data)
    assert response.status_code == 200
    created_user = response.json()
    assert created_user["email"] == user_data["email"]
    assert "id" in created_user
    assert "hashed_password" not in created_user # Ensure password is not returned

    db_user = crud.get_user_by_email(db_session_user, email=user_data["email"])
    assert db_user is not None
    assert db_user.email == user_data["email"]

def test_create_user_duplicate_email(client: TestClient, db_session_user: Session):
    """Test error on creating a user with a duplicate email."""
    user_data = {"email": "duplicate@example.com", "password": "password123", "name": "Duplicate User"}
    response1 = client.post(f"{API_V1_STR}/users/", json=user_data)
    assert response1.status_code == 200

    response2 = client.post(f"{API_V1_STR}/users/", json=user_data)
    assert response2.status_code == 400
    error_detail = response2.json()
    assert "Email already registered" in error_detail["detail"]

def test_get_users_empty(client: TestClient):
    """Test getting an empty list of users."""
    response = client.get(f"{API_V1_STR}/users/")
    assert response.status_code == 200
    assert response.json() == []

def test_get_users_multiple(client: TestClient, db_session_user: Session):
    """Test getting a list with multiple users."""
    user_data1 = {"email": "user1@example.com", "password": "password123", "name": "User 1"}
    user_data2 = {"email": "user2@example.com", "password": "password456", "name": "User 2"}

    client.post(f"{API_V1_STR}/users/", json=user_data1)
    client.post(f"{API_V1_STR}/users/", json=user_data2)

    response = client.get(f"{API_V1_STR}/users/")
    assert response.status_code == 200
    users_list = response.json()
    assert len(users_list) == 2
    emails = [user["email"] for user in users_list]
    assert user_data1["email"] in emails
    assert user_data2["email"] in emails

def test_get_user_by_id_found(client: TestClient, db_session_user: Session):
    """Test getting a user by ID when the user exists."""
    user_data = {"email": "getme@example.com", "password": "password123", "name": "Get Me User"}
    create_response = client.post(f"{API_V1_STR}/users/", json=user_data)
    created_user_id = create_response.json()["id"]

    response = client.get(f"{API_V1_STR}/users/{created_user_id}")
    assert response.status_code == 200
    retrieved_user = response.json()
    assert retrieved_user["id"] == created_user_id
    assert retrieved_user["email"] == user_data["email"]

def test_get_user_by_id_not_found(client: TestClient):
    """Test getting a user by ID when the user does not exist (404)."""
    non_existent_user_id = 99999
    response = client.get(f"{API_V1_STR}/users/{non_existent_user_id}")
    assert response.status_code == 404
    error_detail = response.json()
    assert "User not found" in error_detail["detail"]
