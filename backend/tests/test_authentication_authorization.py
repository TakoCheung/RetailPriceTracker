"""
TDD tests for Authentication and Authorization features.
This module tests JWT authentication, role-based access control, GitHub OAuth integration,
and comprehensive security features following TDD principles.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from app.database import get_session
from app.main import app
from app.models import User, UserRole
from app.services.auth import AuthService
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

# Create a test engine for auth tests
AUTH_TEST_DATABASE_URL = "sqlite:///auth_test.db"
auth_test_engine = create_engine(AUTH_TEST_DATABASE_URL, echo=False)


@pytest.fixture(scope="function", autouse=True)
def setup_auth_test_db():
    """Setup test database for each auth test."""
    SQLModel.metadata.drop_all(auth_test_engine)
    SQLModel.metadata.create_all(auth_test_engine)
    yield
    SQLModel.metadata.drop_all(auth_test_engine)


@pytest.fixture
def auth_client():
    """Create a test client with database dependency override for auth tests."""

    def get_test_session():
        SessionLocal = sessionmaker(bind=auth_test_engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = get_test_session
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_test_data():
    """Test data for authentication tests."""
    return {
        "users": [
            {
                "email": "admin@example.com",
                "name": "Admin User",
                "role": UserRole.ADMIN,
                "github_id": "123456",
                "is_active": True,
            },
            {
                "email": "user@example.com",
                "name": "Regular User",
                "role": UserRole.VIEWER,
                "github_id": "654321",
                "is_active": True,
            },
            {
                "email": "inactive@example.com",
                "name": "Inactive User",
                "role": UserRole.VIEWER,
                "github_id": "999999",
                "is_active": False,
            },
        ],
        "jwt_secret": "test-secret-key",
        "github_oauth_data": {
            "access_token": "gho_test_token",
            "user_data": {
                "id": 789012,
                "login": "testuser",
                "email": "oauth@example.com",
                "name": "OAuth Test User",
            },
        },
    }


class TestJWTAuthentication:
    """Test JWT token-based authentication."""

    def test_create_access_token(self, auth_test_data):
        """Test JWT access token creation."""
        auth_service = AuthService()
        user_data = {"user_id": 1, "email": "test@example.com", "role": "viewer"}

        token = auth_service.create_access_token(user_data)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify token
        decoded = auth_service.decode_token(token)
        assert decoded["user_id"] == 1
        assert decoded["email"] == "test@example.com"
        assert decoded["role"] == "viewer"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_create_refresh_token(self, auth_test_data):
        """Test JWT refresh token creation."""
        auth_service = AuthService()
        user_data = {"user_id": 1, "email": "test@example.com"}

        token = auth_service.create_refresh_token(user_data)

        assert token is not None
        assert isinstance(token, str)

        # Refresh tokens should have longer expiry
        decoded = auth_service.decode_token(token)
        exp_time = datetime.fromtimestamp(decoded["exp"])
        current_time = datetime.utcnow()
        time_diff = exp_time - current_time
        assert time_diff.total_seconds() >= (
            6 * 24 * 3600
        )  # At least 6 days (allowing for timing)

    def test_token_expiration(self, auth_test_data):
        """Test token expiration handling."""
        auth_service = AuthService()

        # Create expired token
        user_data = {"user_id": 1, "email": "test@example.com"}
        expired_token = auth_service.create_access_token(
            user_data,
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        # Should raise exception when decoding expired token
        with pytest.raises(jwt.ExpiredSignatureError):
            auth_service.decode_token(expired_token)

    def test_invalid_token_signature(self, auth_test_data):
        """Test handling of tokens with invalid signatures."""
        auth_service = AuthService()

        # Create token with wrong secret
        user_data = {"user_id": 1, "email": "test@example.com"}
        token = jwt.encode(user_data, "wrong-secret", algorithm="HS256")

        # Should raise exception for invalid signature
        with pytest.raises(jwt.JWTError):
            auth_service.decode_token(token)

    def test_malformed_token(self, auth_test_data):
        """Test handling of malformed tokens."""
        auth_service = AuthService()

        # Test various malformed tokens
        malformed_tokens = [
            "not.a.token",
            "invalid-token",
            "",
            None,
        ]

        for token in malformed_tokens:
            with pytest.raises((jwt.JWTError, ValueError, TypeError)):
                auth_service.decode_token(token)


class TestPasswordAuthentication:
    """Test password-based authentication."""

    def test_hash_password(self, auth_test_data):
        """Test password hashing."""
        auth_service = AuthService()
        password = "securepassword123"

        hashed = auth_service.hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$")  # bcrypt hash format

    def test_verify_password(self, auth_test_data):
        """Test password verification."""
        auth_service = AuthService()
        password = "securepassword123"
        wrong_password = "wrongpassword"

        hashed = auth_service.hash_password(password)

        # Correct password should verify
        assert auth_service.verify_password(password, hashed) is True

        # Wrong password should not verify
        assert auth_service.verify_password(wrong_password, hashed) is False

    def test_password_complexity_validation(self, auth_test_data):
        """Test password complexity validation logic."""
        auth_service = AuthService()

        # Valid passwords
        valid_passwords = ["SecurePass123", "MyPassword1", "TestPass99", "Complex1Pass"]

        for password in valid_passwords:
            assert auth_service.validate_password_strength(password) is True

        # Invalid passwords
        invalid_passwords = [
            "12345",  # Too short
            "password",  # No numbers, no uppercase
            "PASSWORD123",  # No lowercase
            "password123",  # No uppercase
            "PASSWORDABC",  # No numbers, no lowercase
            "Pass1",  # Too short but has all character types
        ]

        for password in invalid_passwords:
            assert auth_service.validate_password_strength(password) is False

    def test_authenticate_user_with_password(self, auth_client, auth_test_data):
        """Test user authentication with email and password."""
        # Create user with password
        auth_service = AuthService()
        password = "testpassword123"
        hashed_password = auth_service.hash_password(password)

        user = User(
            email="test@example.com",
            name="Test User",
            password_hash=hashed_password,
            role=UserRole.VIEWER,
        )

        # Use auth_client's session directly (sync session for auth tests)
        SessionLocal = sessionmaker(bind=auth_test_engine)
        with SessionLocal() as session:
            session.add(user)
            session.commit()

        # Test authentication endpoint
        response = auth_client.post(
            "/api/auth/login", json={"email": "test@example.com", "password": password}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_authenticate_with_wrong_password(
        self, client, db_session, auth_test_data
    ):
        """Test authentication with incorrect password."""
        # Create user
        auth_service = AuthService()
        hashed_password = auth_service.hash_password("correctpassword")

        user = User(
            email="test@example.com",
            name="Test User",
            password_hash=hashed_password,
            role=UserRole.VIEWER,
        )
        db_session.add(user)
        await db_session.commit()

        # Test with wrong password
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, client, db_session, auth_test_data):
        """Test that inactive users cannot authenticate."""
        auth_service = AuthService()
        hashed_password = auth_service.hash_password("password123")

        user = User(
            email="inactive@example.com",
            name="Inactive User",
            password_hash=hashed_password,
            role=UserRole.VIEWER,
            is_active=False,
        )
        db_session.add(user)
        await db_session.commit()

        response = client.post(
            "/api/auth/login",
            json={"email": "inactive@example.com", "password": "password123"},
        )

        assert response.status_code == 401
        assert "Account is inactive" in response.json()["detail"]


class TestGitHubOAuth:
    """Test GitHub OAuth integration."""

    @patch("httpx.AsyncClient.get")
    def test_github_oauth_flow_initiation(self, mock_get, client, auth_test_data):
        """Test GitHub OAuth flow initiation."""
        response = client.get("/api/auth/github/login")

        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "github.com/login/oauth/authorize" in data["authorization_url"]

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_github_oauth_callback_new_user(
        self, mock_get, mock_post, client, db_session, auth_test_data
    ):
        """Test GitHub OAuth callback with new user."""
        github_data = auth_test_data["github_oauth_data"]

        # Mock GitHub API responses
        mock_post.return_value.json.return_value = {
            "access_token": github_data["access_token"]
        }
        mock_post.return_value.status_code = 200

        mock_get.return_value.json.return_value = github_data["user_data"]
        mock_get.return_value.status_code = 200

        response = client.get(
            "/api/auth/github/callback?code=test_code&state=test_state"
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == github_data["user_data"]["email"]
        assert data["user"]["github_id"] == str(github_data["user_data"]["id"])

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    @pytest.mark.asyncio
    async def test_github_oauth_callback_existing_user(
        self, mock_get, mock_post, client, db_session, auth_test_data
    ):
        """Test GitHub OAuth callback with existing user."""
        github_data = auth_test_data["github_oauth_data"]

        # Create existing user
        existing_user = User(
            email=github_data["user_data"]["email"],
            name=github_data["user_data"]["name"],
            github_id=str(github_data["user_data"]["id"]),
            role=UserRole.VIEWER,
        )
        db_session.add(existing_user)
        await db_session.commit()

        # Mock GitHub API responses
        mock_post.return_value.json.return_value = {
            "access_token": github_data["access_token"]
        }
        mock_post.return_value.status_code = 200

        mock_get.return_value.json.return_value = github_data["user_data"]
        mock_get.return_value.status_code = 200

        response = client.get(
            "/api/auth/github/callback?code=test_code&state=test_state"
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["id"] == existing_user.id

    @patch("httpx.AsyncClient.post")
    def test_github_oauth_error_handling(self, mock_post, client, auth_test_data):
        """Test GitHub OAuth error handling."""
        # Mock GitHub API error
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {"error": "invalid_grant"}

        response = client.get(
            "/api/auth/github/callback?code=invalid_code&state=test_state"
        )

        assert response.status_code == 400
        assert "GitHub OAuth error" in response.json()["detail"]


class TestRoleBasedAccessControl:
    """Test role-based access control (RBAC)."""

    @pytest.mark.asyncio
    async def test_admin_access_to_admin_endpoints(
        self, client, db_session, auth_test_data
    ):
        """Test that admin users can access admin-only endpoints."""
        # Create admin user and get token
        admin_user = User(
            email="admin@example.com", name="Admin User", role=UserRole.ADMIN
        )
        db_session.add(admin_user)
        await db_session.commit()

        auth_service = AuthService()
        token = auth_service.create_access_token(
            {
                "user_id": admin_user.id,
                "email": admin_user.email,
                "role": admin_user.role.value,
            }
        )

        # Test admin endpoint access
        response = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_denied_admin_access(self, client, db_session, auth_test_data):
        """Test that viewer users are denied admin endpoint access."""
        # Create viewer user and get token
        viewer_user = User(
            email="viewer@example.com", name="Viewer User", role=UserRole.VIEWER
        )
        db_session.add(viewer_user)
        await db_session.commit()

        auth_service = AuthService()
        token = auth_service.create_access_token(
            {
                "user_id": viewer_user.id,
                "email": viewer_user.email,
                "role": viewer_user.role.value,
            }
        )

        # Test admin endpoint access denied
        response = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_unauthenticated_access_denied(self, client, auth_test_data):
        """Test that unauthenticated requests are denied."""
        # Test protected endpoint without token
        response = client.get("/api/users/profile")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_user_can_access_own_data(self, client, db_session, auth_test_data):
        """Test that users can access their own data."""
        # Create user and get token
        user = User(email="user@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        auth_service = AuthService()
        token = auth_service.create_access_token(
            {"user_id": user.id, "email": user.email, "role": user.role.value}
        )

        # Test accessing own profile
        response = client.get(
            "/api/users/profile", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user.email

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_user_data(
        self, client, db_session, auth_test_data
    ):
        """Test that users cannot access other users' data."""
        # Create two users
        user1 = User(email="user1@example.com", name="User 1", role=UserRole.VIEWER)
        user2 = User(email="user2@example.com", name="User 2", role=UserRole.VIEWER)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Get token for user1
        auth_service = AuthService()
        token = auth_service.create_access_token(
            {"user_id": user1.id, "email": user1.email, "role": user1.role.value}
        )

        # Try to access user2's data
        response = client.get(
            f"/api/users/{user2.id}", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]


class TestTokenRefresh:
    """Test JWT token refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self, client, db_session, auth_test_data):
        """Test refreshing a valid refresh token."""
        # Create user
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        # Create refresh token
        auth_service = AuthService()
        refresh_token = auth_service.create_refresh_token(
            {"user_id": user.id, "email": user.email}
        )

        # Test refresh endpoint
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, client, auth_test_data):
        """Test refreshing an expired token."""
        auth_service = AuthService()

        # Create expired refresh token
        expired_token = auth_service.create_refresh_token(
            {"user_id": 1, "email": "test@example.com"},
            expires_delta=timedelta(seconds=-1),
        )

        response = client.post(
            "/api/auth/refresh", json={"refresh_token": expired_token}
        )

        assert response.status_code == 401
        assert "Token expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client, auth_test_data):
        """Test refreshing an invalid token."""
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]


class TestAccountManagement:
    """Test user account management features."""

    @pytest.mark.asyncio
    async def test_user_registration(self, client, db_session, auth_test_data):
        """Test user registration with email and password."""
        registration_data = {
            "email": "newuser@example.com",
            "name": "New User",
            "password": "securepassword123",
        }

        response = client.post("/api/auth/register", json=registration_data)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == registration_data["email"]
        assert data["name"] == registration_data["name"]
        assert data["role"] == UserRole.VIEWER.value
        assert "password" not in data  # Password should not be returned

    @pytest.mark.asyncio
    async def test_duplicate_email_registration(
        self, client, db_session, auth_test_data
    ):
        """Test that duplicate email registration is rejected."""
        # Create existing user
        existing_user = User(
            email="existing@example.com", name="Existing User", role=UserRole.VIEWER
        )
        db_session.add(existing_user)
        await db_session.commit()

        # Try to register with same email
        response = client.post(
            "/api/auth/register",
            json={
                "email": "existing@example.com",
                "name": "New User",
                "password": "password123",
            },
        )

        assert response.status_code == 409
        assert "Email already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_password_change(self, client, db_session, auth_test_data):
        """Test password change functionality."""
        # Create user with password
        auth_service = AuthService()
        old_password = "oldpassword123"
        hashed_password = auth_service.hash_password(old_password)

        user = User(
            email="user@example.com",
            name="Test User",
            password_hash=hashed_password,
            role=UserRole.VIEWER,
        )
        db_session.add(user)
        await db_session.commit()

        # Get auth token
        token = auth_service.create_access_token(
            {"user_id": user.id, "email": user.email, "role": user.role.value}
        )

        # Change password
        response = client.put(
            "/api/auth/change-password",
            json={"current_password": old_password, "new_password": "newpassword123"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Password updated successfully"

    @pytest.mark.asyncio
    async def test_account_deactivation(self, client, db_session, auth_test_data):
        """Test user account deactivation."""
        # Create admin user
        admin_user = User(
            email="admin@example.com", name="Admin User", role=UserRole.ADMIN
        )

        # Create target user
        target_user = User(
            email="target@example.com", name="Target User", role=UserRole.VIEWER
        )

        db_session.add_all([admin_user, target_user])
        await db_session.commit()

        # Get admin token
        auth_service = AuthService()
        admin_token = auth_service.create_access_token(
            {
                "user_id": admin_user.id,
                "email": admin_user.email,
                "role": admin_user.role.value,
            }
        )

        # Deactivate target user
        response = client.put(
            f"/api/admin/users/{target_user.id}/deactivate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False


class TestSecurityFeatures:
    """Test security features and protections."""

    @pytest.mark.asyncio
    async def test_rate_limiting_login_attempts(self, client, auth_test_data):
        """Test rate limiting on login attempts."""
        login_data = {"email": "test@example.com", "password": "wrongpassword"}

        # Make multiple failed attempts
        responses = []
        for _ in range(6):  # Exceed rate limit
            response = client.post("/api/auth/login", json=login_data)
            responses.append(response)

        # Later attempts should be rate limited
        assert any(r.status_code == 429 for r in responses[-2:])

    @pytest.mark.asyncio
    async def test_password_complexity_requirements(self, client, auth_test_data):
        """Test password complexity validation."""
        weak_passwords = [
            "123456",  # Too short
            "password",  # No numbers/symbols
            "PASSWORD123",  # No lowercase
            "password123",  # No uppercase
        ]

        for weak_password in weak_passwords:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": f"test{weak_password}@example.com",
                    "name": "Test User",
                    "password": weak_password,
                },
            )

            assert response.status_code == 422
            assert "Password does not meet requirements" in response.json()["detail"]

    def test_jwt_token_blacklisting(self, auth_test_data):
        """Test JWT token blacklisting on logout."""
        auth_service = AuthService()

        # Create token
        token = auth_service.create_access_token(
            {"user_id": 1, "email": "test@example.com", "role": "viewer"}
        )

        # Token should be valid initially
        decoded = auth_service.decode_token(token)
        assert decoded["user_id"] == 1

        # Blacklist token
        auth_service.blacklist_token(token)

        # Token should now be invalid
        with pytest.raises(jwt.JWTError):
            auth_service.verify_token_not_blacklisted(token)

    @pytest.mark.asyncio
    async def test_logout_endpoint(self, client, db_session, auth_test_data):
        """Test logout endpoint blacklists tokens."""
        # Create user and get token
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        auth_service = AuthService()
        token = auth_service.create_access_token(
            {"user_id": user.id, "email": user.email, "role": user.role.value}
        )

        # Logout
        response = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"

        # Token should now be blacklisted
        response = client.get(
            "/api/users/profile", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestMiddlewareIntegration:
    """Test authentication middleware integration."""

    @pytest.mark.asyncio
    async def test_auth_middleware_injects_user(
        self, client, db_session, auth_test_data
    ):
        """Test that auth middleware properly injects user data."""
        # Create user
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        # Get token
        auth_service = AuthService()
        token = auth_service.create_access_token(
            {"user_id": user.id, "email": user.email, "role": user.role.value}
        )

        # Make authenticated request
        response = client.get(
            "/api/users/profile", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["email"] == user.email

    @pytest.mark.asyncio
    async def test_auth_middleware_handles_missing_token(self, client, auth_test_data):
        """Test auth middleware handles missing Authorization header."""
        response = client.get("/api/users/profile")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_auth_middleware_handles_malformed_header(
        self, client, auth_test_data
    ):
        """Test auth middleware handles malformed Authorization header."""
        malformed_headers = [
            {"Authorization": "InvalidFormat"},
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "Basic token"},  # Wrong type
        ]

        for headers in malformed_headers:
            response = client.get("/api/users/profile", headers=headers)
            assert response.status_code == 401


class TestAdminEndpoints:
    """Test admin-only endpoints and functionality."""

    @pytest.mark.asyncio
    async def test_list_all_users(self, client, db_session, auth_test_data):
        """Test admin can list all users."""
        # Create admin and regular users
        admin_user = User(email="admin@example.com", name="Admin", role=UserRole.ADMIN)
        user1 = User(email="user1@example.com", name="User 1", role=UserRole.VIEWER)
        user2 = User(email="user2@example.com", name="User 2", role=UserRole.VIEWER)

        db_session.add_all([admin_user, user1, user2])
        await db_session.commit()

        # Get admin token
        auth_service = AuthService()
        token = auth_service.create_access_token(
            {
                "user_id": admin_user.id,
                "email": admin_user.email,
                "role": admin_user.role.value,
            }
        )

        # List users
        response = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 3  # admin + 2 users
        assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_update_user_role(self, client, db_session, auth_test_data):
        """Test admin can update user roles."""
        # Create admin and target user
        admin_user = User(email="admin@example.com", name="Admin", role=UserRole.ADMIN)
        target_user = User(email="user@example.com", name="User", role=UserRole.VIEWER)

        db_session.add_all([admin_user, target_user])
        await db_session.commit()

        # Get admin token
        auth_service = AuthService()
        token = auth_service.create_access_token(
            {
                "user_id": admin_user.id,
                "email": admin_user.email,
                "role": admin_user.role.value,
            }
        )

        # Update user role
        response = client.put(
            f"/api/admin/users/{target_user.id}/role",
            json={"role": UserRole.ADMIN.value},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == UserRole.ADMIN.value
