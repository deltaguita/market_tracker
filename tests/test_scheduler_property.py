#!/usr/bin/env python3
"""
Property-based test for Schedule Due Calculation

Feature: amazon-scraper-refactor
Property 12: Schedule Due Calculation
Validates: Requirements 10.2, 10.5

*For any* source with `schedule_interval_hours` = H and `last_run_time` = T,
the source SHALL be marked as "due for scraping" if and only if (current_time - T) >= H hours.
"""
import sys
import os
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume

from core.scheduler import (
    is_due_for_scraping,
    record_run_time,
    get_last_run_time,
    clear_schedule_state,
)


# Strategies for generating test data
source_strategy = st.sampled_from(["amazon_us", "mercari_jp", "test_source"])
interval_hours_strategy = st.integers(min_value=1, max_value=168)  # 1 hour to 1 week
hours_since_last_run_strategy = st.floats(min_value=0.0, max_value=336.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=100)
@given(
    source=source_strategy,
    interval_hours=interval_hours_strategy,
    hours_since_last_run=hours_since_last_run_strategy
)
def test_schedule_due_calculation(source, interval_hours, hours_since_last_run):
    """
    Feature: amazon-scraper-refactor
    Property 12: Schedule Due Calculation
    Validates: Requirements 10.2, 10.5
    
    For any source with schedule_interval_hours = H and last_run_time = T,
    the source is marked as "due for scraping" if and only if (current_time - T) >= H hours.
    """
    # Create a temporary schedule file for isolation
    temp_dir = tempfile.mkdtemp()
    schedule_file = os.path.join(temp_dir, "schedule_state.json")
    
    try:
        # Set up: define current_time and last_run_time
        current_time = datetime(2025, 1, 14, 12, 0, 0)
        last_run_time = current_time - timedelta(hours=hours_since_last_run)
        
        # Record the last run time
        record_run_time(source, last_run_time, schedule_file)
        
        # Check if due for scraping
        is_due = is_due_for_scraping(
            source=source,
            interval_hours=interval_hours,
            schedule_file=schedule_file,
            current_time=current_time
        )
        
        # Property: due if and only if (current_time - last_run_time) >= interval_hours
        expected_due = hours_since_last_run >= interval_hours
        
        assert is_due == expected_due, (
            f"Source '{source}' with interval {interval_hours}h and "
            f"{hours_since_last_run:.2f}h since last run: "
            f"is_due={is_due}, expected={expected_due}"
        )
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    source=source_strategy,
    interval_hours=interval_hours_strategy
)
def test_schedule_due_no_previous_run(source, interval_hours):
    """
    Feature: amazon-scraper-refactor
    Property 12: Schedule Due Calculation (no previous run case)
    Validates: Requirements 10.2, 10.5
    
    When there is no previous run recorded, the source should always be due for scraping.
    """
    # Create a temporary schedule file for isolation
    temp_dir = tempfile.mkdtemp()
    schedule_file = os.path.join(temp_dir, "schedule_state.json")
    
    try:
        current_time = datetime(2025, 1, 14, 12, 0, 0)
        
        # Don't record any run time - simulate first run
        is_due = is_due_for_scraping(
            source=source,
            interval_hours=interval_hours,
            schedule_file=schedule_file,
            current_time=current_time
        )
        
        # Property: always due when no previous run
        assert is_due is True, (
            f"Source '{source}' with no previous run should be due, but got is_due={is_due}"
        )
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    source=source_strategy,
    interval_hours=interval_hours_strategy,
    exact_boundary_offset_seconds=st.integers(min_value=-60, max_value=60)
)
def test_schedule_due_boundary_condition(source, interval_hours, exact_boundary_offset_seconds):
    """
    Feature: amazon-scraper-refactor
    Property 12: Schedule Due Calculation (boundary condition)
    Validates: Requirements 10.2, 10.5
    
    Test the exact boundary: due if and only if time elapsed >= interval.
    """
    # Create a temporary schedule file for isolation
    temp_dir = tempfile.mkdtemp()
    schedule_file = os.path.join(temp_dir, "schedule_state.json")
    
    try:
        # Set up times at exact boundary with small offset
        current_time = datetime(2025, 1, 14, 12, 0, 0)
        # last_run_time is exactly interval_hours ago, plus/minus offset
        last_run_time = current_time - timedelta(hours=interval_hours) - timedelta(seconds=exact_boundary_offset_seconds)
        
        # Record the last run time
        record_run_time(source, last_run_time, schedule_file)
        
        # Check if due for scraping
        is_due = is_due_for_scraping(
            source=source,
            interval_hours=interval_hours,
            schedule_file=schedule_file,
            current_time=current_time
        )
        
        # Calculate actual time elapsed
        time_elapsed = current_time - last_run_time
        interval_duration = timedelta(hours=interval_hours)
        
        # Property: due if and only if time_elapsed >= interval_duration
        expected_due = time_elapsed >= interval_duration
        
        assert is_due == expected_due, (
            f"Source '{source}' at boundary (offset={exact_boundary_offset_seconds}s): "
            f"elapsed={time_elapsed}, interval={interval_duration}, "
            f"is_due={is_due}, expected={expected_due}"
        )
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
