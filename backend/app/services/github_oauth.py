"""
GitHub OAuth service for handling GitHub authentication flow.
Manages OAuth authorization, token exchange, and user data retrieval.
"""

import os
from typing import Any, Dict
from urllib.parse import urlencode

import httpx


class GitHubOAuthService:
    """Service for handling GitHub OAuth operations."""

    def __init__(self):
        self.client_id = os.getenv("GITHUB_CLIENT_ID", "")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("GITHUB_REDIRECT_URI", "")
        self.scope = "user:email"

    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }

        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                },
            )

            if response.status_code != 200:
                raise Exception("Failed to exchange code for token")

            data = response.json()
            return data["access_token"]

    async def get_user_data(self, access_token: str) -> Dict[str, Any]:
        """Fetch user data from GitHub using access token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}"},
            )

            if response.status_code != 200:
                raise Exception("Failed to fetch user data")

            return response.json()
