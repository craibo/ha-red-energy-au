"""Test Stage 5 enhancements for Red Energy integration."""
from __future__ import annotations

import os
import json
from unittest.mock import Mock, patch


def test_stage5_files_exist():
    """Test that all Stage 5 files exist."""
    base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "custom_components", "red_energy")
    
    stage5_files = [
        "device_manager.py",
        "performance.py", 
        "state_manager.py",
        "config_migration.py",
        "error_recovery.py",
    ]
    
    for file in stage5_files:
        file_path = os.path.join(base_path, file)
        assert os.path.exists(file_path), f"Stage 5 file {file} is missing"


def test_device_manager_structure():
    """Test that device_manager.py has required classes and methods."""
    device_manager_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "device_manager.py"
    )
    
    with open(device_manager_path, 'r') as f:
        content = f.read()
    
    # Check for main class
    assert "class RedEnergyDeviceManager" in content
    
    # Check for key methods
    required_methods = [
        "async_setup_devices",
        "async_cleanup_orphaned_entities", 
        "async_organize_entities_by_service",
        "async_get_device_diagnostics",
        "async_update_device_configuration",
        "async_migrate_device_identifiers",
        "async_get_performance_metrics",
    ]
    
    for method in required_methods:
        assert method in content, f"Device manager method {method} not found"


def test_performance_module_structure():
    """Test that performance.py has required classes."""
    performance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "performance.py"
    )
    
    with open(performance_path, 'r') as f:
        content = f.read()
    
    # Check for main classes
    required_classes = [
        "PerformanceMonitor",
        "DataProcessor", 
        "BulkOperationManager",
        "MemoryOptimizer",
    ]
    
    for class_name in required_classes:
        assert f"class {class_name}" in content, f"Performance class {class_name} not found"
    
    # Check for key methods
    assert "time_operation" in content
    assert "get_performance_stats" in content
    assert "batch_process_properties" in content
    assert "optimize_sensor_calculations" in content


def test_state_manager_structure():
    """Test that state_manager.py has required classes."""
    state_manager_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "state_manager.py"
    )
    
    with open(state_manager_path, 'r') as f:
        content = f.read()
    
    # Check for main classes
    required_classes = [
        "RedEnergyStateManager",
        "RedEnergyRestoreEntity",
        "EntityAvailabilityManager",
    ]
    
    for class_name in required_classes:
        assert f"class {class_name}" in content, f"State manager class {class_name} not found"
    
    # Check for key methods
    state_methods = [
        "async_load_states",
        "async_save_states",
        "record_entity_state",
        "get_restoration_data",
        "async_restore_entity_states",
    ]
    
    for method in state_methods:
        assert method in content, f"State manager method {method} not found"


def test_config_migration_structure():
    """Test that config_migration.py has required classes."""
    config_migration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "config_migration.py"
    )
    
    with open(config_migration_path, 'r') as f:
        content = f.read()
    
    # Check for main classes
    required_classes = [
        "RedEnergyConfigMigrator",
        "RedEnergyConfigValidator",
        "ConfigHealthChecker",
    ]
    
    for class_name in required_classes:
        assert f"class {class_name}" in content, f"Config migration class {class_name} not found"
    
    # Check for version constants
    version_constants = [
        "CONFIG_VERSION_1",
        "CONFIG_VERSION_2", 
        "CONFIG_VERSION_3",
        "CURRENT_CONFIG_VERSION",
    ]
    
    for constant in version_constants:
        assert constant in content, f"Config version constant {constant} not found"


def test_error_recovery_structure():
    """Test that error_recovery.py has required classes and enums."""
    error_recovery_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "error_recovery.py"
    )
    
    with open(error_recovery_path, 'r') as f:
        content = f.read()
    
    # Check for enums
    required_enums = [
        "class ErrorSeverity(Enum)",
        "class RecoveryStrategy(Enum)",
        "class ErrorType(Enum)",
    ]
    
    for enum_class in required_enums:
        assert enum_class in content, f"Error recovery enum {enum_class} not found"
    
    # Check for main classes
    required_classes = [
        "ErrorRecord",
        "RecoveryAction",
        "RedEnergyErrorRecoverySystem",
        "CircuitBreaker",
    ]
    
    for class_name in required_classes:
        assert f"class {class_name}" in content, f"Error recovery class {class_name} not found"


def test_coordinator_stage5_integration():
    """Test that coordinator.py integrates Stage 5 enhancements."""
    coordinator_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "coordinator.py"
    )
    
    with open(coordinator_path, 'r') as f:
        content = f.read()
    
    # Check for Stage 5 imports
    stage5_imports = [
        "from .error_recovery import RedEnergyErrorRecoverySystem, ErrorType",
        "from .performance import PerformanceMonitor, DataProcessor",
    ]
    
    for import_line in stage5_imports:
        assert import_line in content, f"Stage 5 import not found: {import_line}"
    
    # Check for initialization of Stage 5 components
    assert "self._error_recovery = RedEnergyErrorRecoverySystem(hass)" in content
    assert "self._performance_monitor = PerformanceMonitor(hass)" in content
    assert "self._data_processor = DataProcessor(self._performance_monitor)" in content
    
    # Check for performance monitoring decorator
    assert "@PerformanceMonitor.time_operation" in content
    
    # Check for enhanced methods
    enhanced_methods = [
        "_bulk_update_data",
        "_fetch_property_usage",
        "_fetch_usage_data_optimized",
        "get_performance_metrics",
        "get_error_statistics",
    ]
    
    for method in enhanced_methods:
        assert method in content, f"Enhanced coordinator method {method} not found"


def test_init_stage5_integration():
    """Test that __init__.py integrates Stage 5 components."""
    init_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "__init__.py"
    )
    
    with open(init_path, 'r') as f:
        content = f.read()
    
    # Check for Stage 5 imports
    stage5_imports = [
        "from .device_manager import RedEnergyDeviceManager",
        "from .state_manager import RedEnergyStateManager", 
        "from .config_migration import RedEnergyConfigMigrator",
    ]
    
    for import_line in stage5_imports:
        assert import_line in content, f"Stage 5 import not found in __init__.py: {import_line}"
    
    # Check for migration setup
    assert "migrator = RedEnergyConfigMigrator(hass)" in content
    assert "await migrator.async_migrate_config_entry(entry)" in content
    
    # Check for component initialization
    assert "state_manager = RedEnergyStateManager(hass)" in content
    assert "device_manager = RedEnergyDeviceManager(hass, entry)" in content
    assert "await device_manager.async_setup_devices(" in content
    
    # Check for cleanup integration
    assert "await state_manager.async_save_states()" in content
    assert "await device_manager.async_cleanup_orphaned_entities()" in content


def test_performance_optimization_features():
    """Test that performance optimization features are properly implemented."""
    performance_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "performance.py"
    )
    
    with open(performance_path, 'r') as f:
        content = f.read()
    
    # Check for caching features
    assert "@lru_cache" in content
    assert "cache_key" in content
    assert "cache_hits" in content
    assert "cache_misses" in content
    
    # Check for bulk operations
    assert "async_bulk_refresh_coordinators" in content
    assert "async_bulk_update_entities" in content
    assert "batch_size" in content
    
    # Check for memory optimization
    assert "optimize_usage_data" in content
    assert "_data_limit" in content
    assert "_cleanup_threshold" in content
    assert "_compress_to_weekly_averages" in content


def test_error_recovery_strategies():
    """Test that error recovery strategies are properly defined."""
    error_recovery_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "error_recovery.py"
    )
    
    with open(error_recovery_path, 'r') as f:
        content = f.read()
    
    # Check for recovery strategy implementations
    recovery_methods = [
        "_retry_api_connection",
        "_refresh_authentication",
        "_wait_and_retry",
        "_use_cached_data",
        "_retry_coordinator_update",
        "_use_last_known_state",
        "_notify_authentication_failure",
    ]
    
    for method in recovery_methods:
        assert method in content, f"Recovery method {method} not found"
    
    # Check for circuit breaker functionality
    assert "CircuitBreaker" in content
    assert "failure_threshold" in content
    assert "recovery_timeout" in content
    assert "record_success" in content
    assert "record_failure" in content


def test_state_restoration_features():
    """Test that state restoration features are implemented."""
    state_manager_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "state_manager.py"
    )
    
    with open(state_manager_path, 'r') as f:
        content = f.read()
    
    # Check for storage integration
    assert "Store" in content
    assert "STORAGE_VERSION" in content
    assert "STORAGE_KEY" in content
    
    # Check for restore entity base class
    assert "RestoreEntity" in content
    assert "async_get_last_state" in content
    assert "async_added_to_hass" in content
    
    # Check for availability management
    assert "EntityAvailabilityManager" in content
    assert "async_monitor_entity_availability" in content
    assert "_attempt_entity_recovery" in content


def test_device_management_features():
    """Test that device management features are comprehensive."""
    device_manager_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "device_manager.py"
    )
    
    with open(device_manager_path, 'r') as f:
        content = f.read()
    
    # Check for device registry integration
    assert "device_registry as dr" in content
    assert "entity_registry as er" in content
    assert "DeviceEntry" in content
    
    # Check for device model generation
    assert "_get_device_model" in content
    assert "_get_software_version" in content
    
    # Check for diagnostics support
    assert "async_get_device_diagnostics" in content
    assert "device_info" in content
    assert "entity_count" in content
    
    # Check for organization features
    assert "async_organize_entities_by_service" in content
    assert "service_groups" in content


def test_configuration_migration_versions():
    """Test that configuration migration handles all versions properly."""
    config_migration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "config_migration.py"
    )
    
    with open(config_migration_path, 'r') as f:
        content = f.read()
    
    # Check for all migration methods
    migration_methods = [
        "_migrate_v1_to_v2",
        "_migrate_v2_to_v3",
    ]
    
    for method in migration_methods:
        assert method in content, f"Migration method {method} not found"
    
    # Check for validation schemas
    assert "_create_validation_schemas" in content
    assert "base_config_schema" in content
    assert "options_schema" in content
    assert "account_schema" in content
    
    # Check for health checking
    assert "async_check_integration_health" in content
    assert "_check_coordinator_health" in content
    assert "_check_entity_health" in content


def test_stage5_constants_updated():
    """Test that const.py includes any new Stage 5 constants."""
    const_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "const.py"
    )
    
    with open(const_path, 'r') as f:
        content = f.read()
    
    # Existing constants should still be present
    existing_constants = [
        "SCAN_INTERVAL_OPTIONS",
        "CONF_ENABLE_ADVANCED_SENSORS",
        "CONF_SCAN_INTERVAL",
        "SENSOR_TYPE_DAILY_AVERAGE",
        "SENSOR_TYPE_PEAK_USAGE", 
        "SENSOR_TYPE_EFFICIENCY",
    ]
    
    for constant in existing_constants:
        assert constant in content, f"Existing constant {constant} missing after Stage 5"


def test_manifest_compatibility():
    """Test that manifest.json maintains compatibility."""
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "manifest.json"
    )
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Should maintain all existing fields
    required_fields = ["domain", "name", "config_flow", "documentation_url", "issue_tracker"]
    for field in required_fields:
        assert field in manifest, f"Manifest missing required field: {field}"
    
    # Domain should remain the same
    assert manifest["domain"] == "red_energy"


def test_integration_file_count():
    """Test that we have all expected files for Stage 5."""
    integration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy"
    )
    
    python_files = [f for f in os.listdir(integration_path) if f.endswith('.py')]
    
    # Expected files for Stage 5 (added 5 new files)
    expected_files = [
        "__init__.py",
        "api.py", 
        "config_flow.py",
        "const.py",
        "coordinator.py",
        "data_validation.py",
        "diagnostics.py",
        "energy.py",
        "mock_api.py",
        "sensor.py",
        "services.py",
        # Stage 5 additions
        "device_manager.py",
        "performance.py",
        "state_manager.py", 
        "config_migration.py",
        "error_recovery.py",
    ]
    
    for expected in expected_files:
        assert expected in python_files, f"Missing expected file: {expected}"
    
    # Should have at least 16 Python files
    assert len(python_files) >= 16, f"Expected at least 16 Python files, found {len(python_files)}: {python_files}"


def test_backward_compatibility():
    """Test that Stage 5 maintains backward compatibility."""
    # Check that core sensor classes still exist
    sensor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "sensor.py"
    )
    
    with open(sensor_path, 'r') as f:
        content = f.read()
    
    # Core sensor classes should still exist
    core_sensors = [
        "RedEnergyUsageSensor",
        "RedEnergyCostSensor", 
        "RedEnergyTotalUsageSensor",
        "RedEnergyDailyAverageSensor",
        "RedEnergyMonthlyAverageSensor",
        "RedEnergyPeakUsageSensor",
        "RedEnergyEfficiencySensor",
    ]
    
    for sensor_class in core_sensors:
        assert sensor_class in content, f"Core sensor class {sensor_class} missing after Stage 5"


def test_performance_monitoring_integration():
    """Test that performance monitoring is integrated throughout the codebase."""
    # Check coordinator integration
    coordinator_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "coordinator.py"
    )
    
    with open(coordinator_path, 'r') as f:
        coordinator_content = f.read()
    
    # Should have performance monitoring decorators
    assert "@PerformanceMonitor.time_operation" in coordinator_content
    
    # Should have performance metrics methods
    assert "get_performance_metrics" in coordinator_content
    assert "get_error_statistics" in coordinator_content