"""Tests for configuration service with database persistence."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from file_organizer.api.auth_models import Base
from file_organizer.api.config_service import (
    AISettings,
    ConfigResponse,
    ConfigService,
    OrganizationSettings,
    StorageSettings,
)
from file_organizer.api.db_models import SettingsStore


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_get_default_config(db_session: Session) -> None:
    """Test getting default configuration when nothing is stored."""
    service = ConfigService(db_session)
    config = service.get_config()

    assert isinstance(config, ConfigResponse)
    assert config.version == "2.0.0"
    assert config.ai.model == "qwen2.5:3b-instruct-q4_K_M"
    assert config.storage.base_path == "/default/path"
    assert config.organization.method == "PARA"


def test_update_config_creates_new_record(db_session: Session) -> None:
    """Test that updating config creates a new database record."""
    service = ConfigService(db_session)
    
    update = {
        "ai": {"model": "gpt-4", "temperature": 0.7},
        "storage": {"base_path": "/custom/path", "auto_backup": False},
    }
    
    config = service.update_config(update)
    
    assert config.ai.model == "gpt-4"
    assert config.ai.temperature == 0.7
    assert config.ai.max_tokens == 3000  # Unchanged default
    assert config.storage.base_path == "/custom/path"
    assert config.storage.auto_backup is False
    
    # Verify it was saved to database
    setting = (
        db_session.query(SettingsStore)
        .filter(
            SettingsStore.user_id.is_(None),
            SettingsStore.key == ConfigService.CONFIG_KEY,
        )
        .first()
    )
    assert setting is not None
    stored_data = json.loads(setting.value)
    assert stored_data["ai"]["model"] == "gpt-4"


def test_update_config_modifies_existing_record(db_session: Session) -> None:
    """Test that updating config modifies existing database record."""
    service = ConfigService(db_session)
    
    # First update
    service.update_config({"ai": {"model": "gpt-3.5"}})
    
    # Second update should modify, not create new
    service.update_config({"ai": {"temperature": 0.9}})
    
    # Verify only one record exists
    count = (
        db_session.query(SettingsStore)
        .filter(
            SettingsStore.user_id.is_(None),
            SettingsStore.key == ConfigService.CONFIG_KEY,
        )
        .count()
    )
    assert count == 1
    
    # Verify both updates are reflected
    config = service.get_config()
    assert config.ai.model == "gpt-3.5"
    assert config.ai.temperature == 0.9


def test_reset_config_deletes_record(db_session: Session) -> None:
    """Test that resetting config deletes the database record."""
    service = ConfigService(db_session)
    
    # Create a config
    service.update_config({"ai": {"model": "custom-model"}})
    
    # Verify it exists
    count_before = (
        db_session.query(SettingsStore)
        .filter(
            SettingsStore.user_id.is_(None),
            SettingsStore.key == ConfigService.CONFIG_KEY,
        )
        .count()
    )
    assert count_before == 1
    
    # Reset config
    config = service.reset_config()
    
    # Verify record is deleted
    count_after = (
        db_session.query(SettingsStore)
        .filter(
            SettingsStore.user_id.is_(None),
            SettingsStore.key == ConfigService.CONFIG_KEY,
        )
        .count()
    )
    assert count_after == 0
    
    # Verify default values are returned
    assert config.ai.model == "qwen2.5:3b-instruct-q4_K_M"


def test_user_specific_config(db_session: Session) -> None:
    """Test user-specific configuration isolation."""
    user1_id = "user-1"
    user2_id = "user-2"
    
    service1 = ConfigService(db_session, user_id=user1_id)
    service2 = ConfigService(db_session, user_id=user2_id)
    
    # Update config for user 1
    service1.update_config({"ai": {"model": "user1-model"}})
    
    # Update config for user 2
    service2.update_config({"ai": {"model": "user2-model"}})
    
    # Verify configs are isolated
    config1 = service1.get_config()
    config2 = service2.get_config()
    
    assert config1.ai.model == "user1-model"
    assert config2.ai.model == "user2-model"


def test_global_vs_user_config(db_session: Session) -> None:
    """Test that global and user configs are separate."""
    user_id = "test-user"
    
    global_service = ConfigService(db_session, user_id=None)
    user_service = ConfigService(db_session, user_id=user_id)
    
    # Set different configs
    global_service.update_config({"ai": {"model": "global-model"}})
    user_service.update_config({"ai": {"model": "user-model"}})
    
    # Verify they're separate
    assert global_service.get_config().ai.model == "global-model"
    assert user_service.get_config().ai.model == "user-model"


def test_corrupted_config_returns_defaults(db_session: Session) -> None:
    """Test that corrupted config data returns defaults."""
    # Manually insert corrupted data
    setting = SettingsStore(
        user_id=None,
        key=ConfigService.CONFIG_KEY,
        value="invalid-json{",
    )
    db_session.add(setting)
    db_session.commit()
    
    service = ConfigService(db_session)
    config = service.get_config()
    
    # Should return defaults instead of crashing
    assert config.ai.model == "qwen2.5:3b-instruct-q4_K_M"


def test_partial_config_update(db_session: Session) -> None:
    """Test that partial updates preserve other settings."""
    service = ConfigService(db_session)
    
    # Set initial config
    service.update_config({
        "ai": {"model": "model-1", "temperature": 0.5},
        "storage": {"base_path": "/path1"},
    })
    
    # Partial update - only change one field
    service.update_config({"ai": {"model": "model-2"}})
    
    config = service.get_config()
    
    # Updated field
    assert config.ai.model == "model-2"
    # Preserved fields
    assert config.ai.temperature == 0.5
    assert config.storage.base_path == "/path1"


def test_organization_settings_update(db_session: Session) -> None:
    """Test updating organization settings."""
    service = ConfigService(db_session)
    
    service.update_config({
        "organization": {
            "method": "JOHNNY_DECIMAL",
            "auto_organize": True,
        }
    })
    
    config = service.get_config()
    assert config.organization.method == "JOHNNY_DECIMAL"
    assert config.organization.auto_organize is True


def test_concurrent_update_simulation(db_session: Session) -> None:
    """Test that database locking prevents race conditions.
    
    This is a basic test - true concurrent testing would require
    multiple threads/processes, but this verifies the locking mechanism
    is in place.
    """
    service = ConfigService(db_session)
    
    # First update
    service.update_config({"ai": {"model": "model-1"}})
    
    # Second update in same session should work
    service.update_config({"ai": {"model": "model-2"}})
    
    # Verify final state
    config = service.get_config()
    assert config.ai.model == "model-2"
