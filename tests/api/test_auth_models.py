"""Tests for file_organizer.api.auth_models."""

from __future__ import annotations

import pytest

from file_organizer.api.auth_models import Base, User

pytestmark = pytest.mark.unit


class TestUserModel:
    """Tests for the User ORM model."""

    def test_tablename(self):
        assert User.__tablename__ == "users"

    def test_instantiation_required_fields(self):
        user = User(
            username="alice",
            email="alice@example.com",
            hashed_password="hashed123",
        )
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.hashed_password == "hashed123"

    def test_default_is_active(self):
        col = User.__table__.columns["is_active"]
        assert col.default.arg is True

    def test_default_is_admin(self):
        col = User.__table__.columns["is_admin"]
        assert col.default.arg is False

    def test_full_name_nullable(self):
        col = User.__table__.columns["full_name"]
        assert col.nullable is True

    def test_last_login_nullable(self):
        col = User.__table__.columns["last_login"]
        assert col.nullable is True

    def test_username_unique(self):
        col = User.__table__.columns["username"]
        assert col.unique is True

    def test_email_unique(self):
        col = User.__table__.columns["email"]
        assert col.unique is True

    def test_username_not_nullable(self):
        col = User.__table__.columns["username"]
        assert col.nullable is False

    def test_email_not_nullable(self):
        col = User.__table__.columns["email"]
        assert col.nullable is False

    def test_hashed_password_not_nullable(self):
        col = User.__table__.columns["hashed_password"]
        assert col.nullable is False

    def test_repr(self):
        user = User(username="bob")
        r = repr(user)
        assert "bob" in r

    def test_id_has_default(self):
        col = User.__table__.columns["id"]
        assert col.default is not None

    def test_created_at_has_default(self):
        col = User.__table__.columns["created_at"]
        assert col.default is not None

    def test_base_is_declarative(self):
        # User inherits from the shared Base
        assert hasattr(Base, "metadata")
        assert "users" in Base.metadata.tables
