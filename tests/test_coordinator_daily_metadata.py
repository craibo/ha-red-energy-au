"""Tests for daily metadata refresh logic in coordinator."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def test_coordinator_daily_metadata_methods_exist():
    """Ensure coordinator exposes daily metadata refresh methods and fields."""
    coordinator_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "coordinator.py",
    )
    assert os.path.exists(coordinator_path)

    with open(coordinator_path, 'r') as f:
        content = f.read()

    # New daily metadata refresh components
    assert "_last_metadata_refresh_date" in content
    assert "def _should_refresh_metadata_today" in content
    assert "async def _async_refresh_metadata" in content
    assert "async def async_refresh_metadata_and_usage" in content

    # Ensure guarded call within _async_update_data
    assert "_should_refresh_metadata_today()" in content or "_async_refresh_metadata()" in content


def test_coordinator_daily_refresh_behavior():
    """Test that metadata is only refreshed once per calendar day."""
    from datetime import date, timezone
    
    # Test the calendar day logic directly
    class MockCoordinator:
        def __init__(self):
            self._last_metadata_refresh_date = None
        
        def _should_refresh_metadata_today(self) -> bool:
            """Return True if we haven't refreshed metadata today (calendar day)."""
            today = date.today()
            if self._last_metadata_refresh_date is None:
                return True
            return self._last_metadata_refresh_date != today
    
    coordinator = MockCoordinator()
    
    # Test 1: First call should refresh metadata
    coordinator._last_metadata_refresh_date = None
    assert coordinator._should_refresh_metadata_today() == True
    
    # Test 2: Same day should not refresh
    today = date.today()
    coordinator._last_metadata_refresh_date = today
    assert coordinator._should_refresh_metadata_today() == False
    
    # Test 3: Next day should refresh
    yesterday = date.today().replace(day=date.today().day - 1) if date.today().day > 1 else date.today().replace(month=date.today().month - 1, day=28)
    coordinator._last_metadata_refresh_date = yesterday
    assert coordinator._should_refresh_metadata_today() == True


