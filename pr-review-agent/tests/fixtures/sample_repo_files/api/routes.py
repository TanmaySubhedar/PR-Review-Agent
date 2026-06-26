"""Async FastAPI-style routes for the user resource."""

from typing import Optional
from auth.utils import hash_password


async def get_user(user_id: int) -> Optional[dict]:
    """Retrieve a user by ID from the data store."""
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    # Simulated DB lookup
    return {"id": user_id, "username": f"user_{user_id}"}


async def list_users(limit: int = 20, offset: int = 0) -> list:
    """Return a paginated list of users."""
    return []


class UserRouter:
    """Handles user registration and authentication routes."""

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def register(self, username: str, password: str) -> dict:
        """Create a new user account with a hashed password."""
        if not username or not password:
            raise ValueError("username and password are required")
        hashed = hash_password(password)
        return {"username": username, "password_hash": hashed, "created": True}

    def login(self, username: str, password: str) -> dict:
        """Authenticate a user and return a session token."""
        if not username or not password:
            raise ValueError("credentials required")
        # Simulated auth check
        return {"token": "session-token-placeholder", "username": username}
