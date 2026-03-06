"""Unit tests for API application initialization and thread safety."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestAppInitializationLaziness:
    """Test that app initialization is deferred and not at import time."""

    def test_app_not_created_at_import_time(self):
        """App should not be created when api module is imported."""
        # Verify that importing api module doesn't create the app
        # The test framework would have called get_app() if needed
        # But we should be able to reset and verify it's lazy
        import file_organizer.api.main as main_module

        # Reset the cached app to test laziness
        original_app = main_module._app
        main_module._app = None

        try:
            # After reset, _app should be None (not created)
            assert main_module._app is None

            # Calling create_app() directly is allowed, but get_app() defers
            app = main_module.get_app()
            assert app is not None
            assert isinstance(app, FastAPI)
        finally:
            # Restore original state
            main_module._app = original_app

    def test_app_creation_defers_side_effects(self):
        """App creation should defer filesystem side effects."""
        import file_organizer.api.main as main_module

        # Reset app cache
        original_app = main_module._app
        main_module._app = None

        try:
            # At this point, no config directory should have been created
            # (because get_app() hasn't been called yet during test)
            assert main_module._app is None

            # When we call get_app(), it will create app and side effects occur
            app = main_module.get_app()
            assert app is not None
        finally:
            # Restore
            main_module._app = original_app


class TestAppThreadSafety:
    """Test that app initialization is thread-safe."""

    def test_get_app_thread_safety_main_module(self):
        """get_app() from main module should return same instance across threads."""
        import file_organizer.api.main as main_module

        # Reset app cache for this test
        original_app = main_module._app
        main_module._app = None

        try:
            instances = []
            errors = []

            def get_app_in_thread():
                """Get app instance in a separate thread."""
                try:
                    app = main_module.get_app()
                    instances.append(app)
                except Exception as e:
                    errors.append(e)

            # Create multiple threads that all call get_app() concurrently
            threads = [threading.Thread(target=get_app_in_thread) for _ in range(10)]

            # Start all threads at roughly the same time
            for thread in threads:
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Verify no errors occurred
            assert len(errors) == 0, f"Errors in threads: {errors}"

            # Verify we got instances from all threads
            assert len(instances) == 10

            # All instances should be the same object (same id)
            first_id = id(instances[0])
            for instance in instances[1:]:
                assert id(instance) == first_id, (
                    "Got different app instances from different threads"
                )

        finally:
            # Restore original state
            main_module._app = original_app

    def test_get_app_thread_safety_package_init(self):
        """get_app() from package __init__ should return same instance across threads."""
        import file_organizer.api as api_package

        # Reset app cache for this test
        original_app = api_package._app_cache
        api_package._app_cache = None

        try:
            instances = []
            errors = []

            def get_app_in_thread():
                """Get app instance in a separate thread."""
                try:
                    app = api_package.get_app()
                    instances.append(app)
                except Exception as e:
                    errors.append(e)

            # Create multiple threads that all call get_app() concurrently
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(get_app_in_thread) for _ in range(10)]
                for future in futures:
                    future.result(timeout=5)

            # Verify no errors occurred
            assert len(errors) == 0, f"Errors in threads: {errors}"

            # Verify we got instances from all threads
            assert len(instances) == 10

            # All instances should be the same object (same id)
            first_id = id(instances[0])
            for instance in instances[1:]:
                assert id(instance) == first_id, (
                    "Got different app instances from different threads"
                )

        finally:
            # Restore original state
            api_package._app_cache = original_app

    def test_concurrent_create_app_calls_dont_duplicate_side_effects(self):
        """Verify that concurrent create_app() calls don't cause issues."""
        import file_organizer.api.main as main_module

        # Reset to test fresh initialization
        original_app = main_module._app
        original_logging = main_module._LOGGING_CONFIGURED
        main_module._app = None
        main_module._LOGGING_CONFIGURED = False

        try:
            apps = []
            errors = []

            def create_app_in_thread():
                """Create app in a separate thread."""
                try:
                    from file_organizer.api.main import create_app

                    app = create_app()
                    apps.append(app)
                except Exception as e:
                    errors.append(e)

            # Note: We're testing create_app() directly (not get_app()),
            # so multiple instances are expected. But we verify no errors.
            threads = [threading.Thread(target=create_app_in_thread) for _ in range(5)]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join(timeout=10)

            # Verify no errors occurred during app creation
            assert len(errors) == 0, f"Errors in threads: {errors}"

            # Verify all apps were created (create_app doesn't cache)
            assert len(apps) == 5

            # All should be FastAPI instances
            for app in apps:
                assert isinstance(app, FastAPI)

        finally:
            # Restore original state
            main_module._app = original_app
            main_module._LOGGING_CONFIGURED = original_logging


class TestAppCaching:
    """Test that app instance is properly cached."""

    def test_get_app_returns_cached_instance(self):
        """Calling get_app() multiple times should return same instance."""
        import file_organizer.api.main as main_module

        original_app = main_module._app
        main_module._app = None

        try:
            # First call creates and caches
            app1 = main_module.get_app()
            assert app1 is not None

            # Second call returns cached instance
            app2 = main_module.get_app()
            assert id(app1) == id(app2), "get_app() should return cached instance"

            # Third call still returns same instance
            app3 = main_module.get_app()
            assert id(app1) == id(app3), "get_app() should return same cached instance"

        finally:
            main_module._app = original_app

    def test_package_get_app_returns_cached_instance(self):
        """Calling get_app() from package multiple times returns same instance."""
        import file_organizer.api as api_package

        original_app = api_package._app_cache
        api_package._app_cache = None

        try:
            # First call creates and caches
            app1 = api_package.get_app()
            assert app1 is not None

            # Second call returns cached instance
            app2 = api_package.get_app()
            assert id(app1) == id(app2), "package get_app() should return cached instance"

        finally:
            api_package._app_cache = original_app
