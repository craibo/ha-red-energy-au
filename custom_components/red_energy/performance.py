"""Performance optimization utilities for Red Energy integration."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque
from functools import lru_cache, wraps

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor and optimize performance of Red Energy integration."""
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize performance monitor."""
        self.hass = hass
        self._timing_data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._memory_usage: deque = deque(maxlen=50)
        self._api_calls: Dict[str, int] = defaultdict(int)
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        
    def time_operation(self, operation_name: str):
        """Decorator to time operations."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    self._timing_data[operation_name].append(execution_time)
                    
                    if execution_time > 5.0:  # Log slow operations
                        _LOGGER.warning(
                            "Slow operation detected: %s took %.2fs",
                            operation_name, execution_time
                        )
                    
                    return result
                except Exception as err:
                    execution_time = time.time() - start_time
                    self._timing_data[f"{operation_name}_error"].append(execution_time)
                    raise err
            return wrapper
        return decorator
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        stats = {
            "timing_stats": {},
            "cache_stats": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_ratio": self._cache_hits / (self._cache_hits + self._cache_misses) if (self._cache_hits + self._cache_misses) > 0 else 0
            },
            "api_calls": dict(self._api_calls),
            "total_operations": sum(len(times) for times in self._timing_data.values())
        }
        
        # Calculate timing statistics
        for operation, times in self._timing_data.items():
            if times:
                times_list = list(times)
                stats["timing_stats"][operation] = {
                    "count": len(times_list),
                    "avg_time": sum(times_list) / len(times_list),
                    "min_time": min(times_list),
                    "max_time": max(times_list),
                    "recent_avg": sum(list(times)[-10:]) / min(10, len(times))
                }
        
        return stats


class DataProcessor:
    """Optimized data processing for Red Energy data."""
    
    def __init__(self, performance_monitor: PerformanceMonitor) -> None:
        """Initialize data processor."""
        self._monitor = performance_monitor
        self._processed_cache: Dict[str, Tuple[datetime, Any]] = {}
        self._cache_ttl = timedelta(minutes=5)
    
    @lru_cache(maxsize=128)
    def _calculate_daily_stats(self, usage_data_tuple: Tuple[Tuple[str, float], ...]) -> Dict[str, float]:
        """Calculate daily statistics with caching."""
        usage_data = [{"date": date, "usage": usage} for date, usage in usage_data_tuple]
        
        if not usage_data:
            return {"mean": 0, "std_dev": 0, "min": 0, "max": 0}
        
        usages = [item["usage"] for item in usage_data]
        mean_usage = sum(usages) / len(usages)
        
        if len(usages) > 1:
            variance = sum((x - mean_usage) ** 2 for x in usages) / len(usages)
            std_dev = variance ** 0.5
        else:
            std_dev = 0
        
        return {
            "mean": mean_usage,
            "std_dev": std_dev,
            "min": min(usages),
            "max": max(usages),
            "count": len(usages)
        }
    
    def get_cached_calculation(self, cache_key: str, calculation_func, *args) -> Any:
        """Get cached calculation result or compute if expired."""
        now = dt_util.utcnow()
        
        if cache_key in self._processed_cache:
            cached_time, cached_result = self._processed_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                self._monitor._cache_hits += 1
                return cached_result
        
        # Cache miss - calculate new result
        self._monitor._cache_misses += 1
        result = calculation_func(*args)
        self._processed_cache[cache_key] = (now, result)
        
        return result
    
    def batch_process_properties(
        self, 
        usage_data: Dict[str, Any], 
        selected_accounts: List[str],
        services: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Batch process multiple properties for efficiency."""
        results = {}
        
        # Pre-calculate common data
        current_date = dt_util.now().date()
        
        for account_id in selected_accounts:
            property_data = usage_data.get(account_id, {})
            if not property_data:
                continue
            
            property_results = {}
            
            # Process each service for this property
            for service_type in services:
                service_data = property_data.get("services", {}).get(service_type, {})
                usage_info = service_data.get("usage_data", {})
                daily_data = usage_info.get("usage_data", [])
                
                if not daily_data:
                    continue
                
                # Convert to tuple for caching
                usage_tuple = tuple((item.get("date", ""), item.get("usage", 0)) for item in daily_data)
                cache_key = f"{account_id}_{service_type}_{hash(usage_tuple)}"
                
                # Calculate daily statistics with caching
                daily_stats = self.get_cached_calculation(
                    f"daily_stats_{cache_key}",
                    self._calculate_daily_stats,
                    usage_tuple
                )
                
                property_results[service_type] = {
                    "usage_info": usage_info,
                    "daily_stats": daily_stats,
                    "daily_data": daily_data
                }
            
            results[account_id] = property_results
        
        return results
    
    def optimize_sensor_calculations(
        self, 
        processed_data: Dict[str, Dict[str, Any]],
        advanced_sensors_enabled: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """Optimize sensor value calculations."""
        sensor_values = {}
        
        for account_id, property_data in processed_data.items():
            property_sensors = {}
            
            for service_type, service_data in property_data.items():
                usage_info = service_data["usage_info"]
                daily_stats = service_data["daily_stats"]
                daily_data = service_data["daily_data"]
                
                # Core sensors (always calculated)
                service_sensors = {
                    "daily_usage": self._get_latest_daily_usage(daily_data),
                    "total_cost": usage_info.get("total_cost", 0),
                    "total_usage": usage_info.get("total_usage", 0)
                }
                
                # Advanced sensors (only if enabled)
                if advanced_sensors_enabled and daily_stats["count"] > 0:
                    service_sensors.update({
                        "daily_average": daily_stats["mean"],
                        "monthly_average": daily_stats["mean"] * 30.44,
                        "peak_usage": self._calculate_peak_usage(daily_data),
                        "efficiency": self._calculate_efficiency_rating(daily_stats)
                    })
                
                property_sensors[service_type] = service_sensors
            
            sensor_values[account_id] = property_sensors
        
        return sensor_values
    
    def _get_latest_daily_usage(self, daily_data: List[Dict[str, Any]]) -> float:
        """Get the most recent daily usage value."""
        if not daily_data:
            return 0.0
        
        # Data is typically sorted by date, get the latest
        return daily_data[-1].get("usage", 0.0)
    
    def _calculate_peak_usage(self, daily_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate peak usage with date attribution."""
        if not daily_data:
            return {"usage": 0, "date": None, "cost": 0}
        
        max_entry = max(daily_data, key=lambda x: x.get("usage", 0))
        
        return {
            "usage": max_entry.get("usage", 0),
            "date": max_entry.get("date"),
            "cost": max_entry.get("cost", 0)
        }
    
    def _calculate_efficiency_rating(self, daily_stats: Dict[str, float]) -> Dict[str, Any]:
        """Calculate efficiency rating based on usage consistency."""
        mean_usage = daily_stats["mean"]
        std_dev = daily_stats["std_dev"]
        
        if mean_usage <= 0:
            return {"rating": 0, "variation": "Unknown"}
        
        # Coefficient of variation
        cv = std_dev / mean_usage
        
        # Convert to efficiency percentage (lower variation = higher efficiency)
        efficiency = max(0, min(100, 100 * (1 - cv)))
        
        # Classify variation level
        if cv < 0.15:
            variation = "Low"
        elif cv < 0.30:
            variation = "Medium"
        else:
            variation = "High"
        
        return {
            "rating": round(efficiency, 1),
            "variation": variation,
            "coefficient_of_variation": round(cv, 3),
            "mean_usage": round(mean_usage, 2)
        }
    
    def clear_cache(self) -> int:
        """Clear processing cache and return number of items cleared."""
        cache_size = len(self._processed_cache)
        self._processed_cache.clear()
        self._calculate_daily_stats.cache_clear()
        return cache_size


class BulkOperationManager:
    """Manage bulk operations for multiple properties efficiently."""
    
    def __init__(self, hass: HomeAssistant, performance_monitor: PerformanceMonitor) -> None:
        """Initialize bulk operation manager."""
        self.hass = hass
        self._monitor = performance_monitor
        self._operation_queue: deque = deque()
        self._max_concurrent = 3
    
    async def async_bulk_refresh_coordinators(
        self, 
        coordinators: List[Any], 
        batch_size: int = 3
    ) -> Dict[str, bool]:
        """Refresh multiple coordinators in batches."""
        results = {}
        
        # Process coordinators in batches
        for i in range(0, len(coordinators), batch_size):
            batch = coordinators[i:i + batch_size]
            
            # Create tasks for concurrent execution
            tasks = []
            for coordinator in batch:
                task = asyncio.create_task(
                    self._refresh_single_coordinator(coordinator),
                    name=f"refresh_{coordinator.username}"
                )
                tasks.append((coordinator.username, task))
            
            # Wait for batch completion
            batch_results = await asyncio.gather(
                *[task for _, task in tasks], 
                return_exceptions=True
            )
            
            # Process results
            for (username, _), result in zip(tasks, batch_results):
                if isinstance(result, Exception):
                    _LOGGER.error("Failed to refresh coordinator %s: %s", username, result)
                    results[username] = False
                else:
                    results[username] = result
            
            # Small delay between batches to prevent overwhelming the API
            if i + batch_size < len(coordinators):
                await asyncio.sleep(0.5)
        
        return results
    
    @PerformanceMonitor.time_operation("coordinator_refresh")
    async def _refresh_single_coordinator(self, coordinator) -> bool:
        """Refresh a single coordinator with error handling."""
        try:
            await coordinator.async_refresh()
            return True
        except Exception as err:
            _LOGGER.error("Coordinator refresh failed: %s", err)
            return False
    
    async def async_bulk_update_entities(
        self, 
        entity_updates: Dict[str, Dict[str, Any]]
    ) -> int:
        """Update multiple entities efficiently."""
        updated_count = 0
        
        # Group updates by platform for efficiency
        platform_groups = defaultdict(list)
        for entity_id, update_data in entity_updates.items():
            platform = entity_id.split('.')[0]
            platform_groups[platform].append((entity_id, update_data))
        
        # Process each platform group
        for platform, updates in platform_groups.items():
            try:
                # Batch update entities in the same platform
                for entity_id, update_data in updates:
                    state = self.hass.states.get(entity_id)
                    if state:
                        # Update entity state
                        self.hass.states.async_set(
                            entity_id, 
                            update_data.get("state", state.state),
                            update_data.get("attributes", state.attributes)
                        )
                        updated_count += 1
                
            except Exception as err:
                _LOGGER.error("Failed to bulk update %s entities: %s", platform, err)
        
        return updated_count


class MemoryOptimizer:
    """Optimize memory usage for large datasets."""
    
    def __init__(self) -> None:
        """Initialize memory optimizer."""
        self._data_limit = 1000  # Maximum number of data points to keep
        self._cleanup_threshold = 0.8  # Cleanup when 80% full
    
    def optimize_usage_data(
        self, 
        usage_data: List[Dict[str, Any]], 
        max_days: int = 90
    ) -> List[Dict[str, Any]]:
        """Optimize usage data by limiting size and removing old data."""
        if not usage_data:
            return usage_data
        
        # Sort by date (most recent first)
        sorted_data = sorted(
            usage_data, 
            key=lambda x: x.get("date", ""), 
            reverse=True
        )
        
        # Limit to maximum days
        limited_data = sorted_data[:max_days]
        
        # If still too large, implement data compression
        if len(limited_data) > self._data_limit:
            # Keep daily data for last 30 days, weekly averages for older data
            recent_data = limited_data[:30]
            older_data = limited_data[30:]
            
            # Compress older data to weekly averages
            weekly_data = self._compress_to_weekly_averages(older_data)
            
            limited_data = recent_data + weekly_data
        
        return limited_data
    
    def _compress_to_weekly_averages(
        self, 
        daily_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compress daily data to weekly averages."""
        if not daily_data:
            return []
        
        weekly_groups = defaultdict(list)
        
        for entry in daily_data:
            date_str = entry.get("date", "")
            if not date_str:
                continue
            
            try:
                date_obj = datetime.fromisoformat(date_str).date()
                # Group by week (Monday = 0)
                week_start = date_obj - timedelta(days=date_obj.weekday())
                weekly_groups[week_start].append(entry)
            except (ValueError, TypeError):
                continue
        
        # Calculate weekly averages
        weekly_averages = []
        for week_start, entries in weekly_groups.items():
            if not entries:
                continue
            
            avg_usage = sum(e.get("usage", 0) for e in entries) / len(entries)
            avg_cost = sum(e.get("cost", 0) for e in entries) / len(entries)
            
            weekly_averages.append({
                "date": week_start.isoformat(),
                "usage": round(avg_usage, 2),
                "cost": round(avg_cost, 2),
                "data_type": "weekly_average",
                "days_included": len(entries)
            })
        
        return weekly_averages
    
    def get_memory_usage_stats(self, data_structure: Any) -> Dict[str, Any]:
        """Get memory usage statistics for a data structure."""
        import sys
        
        def get_size(obj, seen=None):
            """Get approximate size of object in bytes."""
            if seen is None:
                seen = set()
            
            obj_id = id(obj)
            if obj_id in seen:
                return 0
            
            seen.add(obj_id)
            size = sys.getsizeof(obj)
            
            if isinstance(obj, dict):
                size += sum(get_size(k, seen) + get_size(v, seen) for k, v in obj.items())
            elif isinstance(obj, (list, tuple, set, frozenset)):
                size += sum(get_size(i, seen) for i in obj)
            
            return size
        
        total_size = get_size(data_structure)
        
        return {
            "total_bytes": total_size,
            "total_mb": round(total_size / (1024 * 1024), 2),
            "object_count": self._count_objects(data_structure),
        }
    
    def _count_objects(self, obj, count=0) -> int:
        """Count total number of objects in a data structure."""
        count += 1
        
        if isinstance(obj, dict):
            for v in obj.values():
                count = self._count_objects(v, count)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                count = self._count_objects(item, count)
        
        return count