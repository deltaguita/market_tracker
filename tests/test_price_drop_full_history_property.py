#!/usr/bin/env python3
"""
Property-based test for Price Drop Notification in Full-History Mode

Feature: amazon-scraper-refactor
Property 11: Price Drop Notification in Full-History Mode
Validates: Requirements 9.4

*For any* price update in "full_history" mode where the new price is lower than
the previous price, the System SHALL trigger a price drop notification.
"""
import sys
import os
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hypothesis import given, strategies as st, settings, assume

from core.storage import ProductStorage


# Strategies for generating test data
source_strategy = st.sampled_from(["amazon_us", "mercari_jp"])


@st.composite
def amazon_product_strategy(draw, product_id=None):
    """Generate a random Amazon product with USD price"""
    if product_id is None:
        product_id = f"B{draw(st.text(alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=9, max_size=9))}"
    price = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return {
        "id": product_id,
        "title": f"Test Product {product_id}",
        "price_usd": round(price, 2),
        "product_url": f"https://www.amazon.com/dp/{product_id}",
    }


@st.composite
def mercari_product_strategy(draw, product_id=None):
    """Generate a random Mercari product with JPY/TWD price"""
    if product_id is None:
        product_id = f"m{draw(st.text(alphabet='0123456789', min_size=10, max_size=10))}"
    price_jpy = draw(st.integers(min_value=100, max_value=100000))
    price_twd = price_jpy // 5  # Approximate conversion
    return {
        "id": product_id,
        "title": f"Test Product {product_id}",
        "price_jpy": price_jpy,
        "price_twd": price_twd,
        "product_url": f"https://jp.mercari.com/item/{product_id}",
    }


@settings(max_examples=100)
@given(
    old_price=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    new_price=st.floats(min_value=1.0, max_value=999.0, allow_nan=False, allow_infinity=False),
)
def test_price_drop_detection_amazon_full_history(old_price, new_price):
    """
    Feature: amazon-scraper-refactor
    Property 11: Price Drop Notification in Full-History Mode
    Validates: Requirements 9.4
    
    For any price update in full_history mode where new_price < old_price,
    the system SHALL detect a price drop.
    """
    # Ensure we have distinct prices for meaningful test
    old_price = round(old_price, 2)
    new_price = round(new_price, 2)
    assume(old_price != new_price)
    
    # Create a temporary database for isolation
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_products.db")
    
    try:
        storage = ProductStorage(db_path=db_path)
        source = "amazon_us"
        product_id = "B0123456789"
        
        # Create initial product with old price
        initial_product = {
            "id": product_id,
            "title": "Test Amazon Product",
            "price_usd": old_price,
            "product_url": f"https://www.amazon.com/dp/{product_id}",
        }
        
        # Insert initial product and record price history
        storage.upsert_product(initial_product, source, tracking_mode="full_history")
        
        # Create updated product with new price
        updated_product = {
            "id": product_id,
            "title": "Test Amazon Product",
            "price_usd": new_price,
            "product_url": f"https://www.amazon.com/dp/{product_id}",
        }
        
        # Detect price drop before upserting
        price_drop_info = storage.detect_price_drop(updated_product, source, tracking_mode="full_history")
        
        # Property: price drop detected if and only if new_price < old_price
        is_price_drop = new_price < old_price
        
        if is_price_drop:
            assert price_drop_info is not None, (
                f"Price drop from {old_price} to {new_price} should be detected"
            )
            assert price_drop_info.get("old_price_usd") == old_price, (
                f"Old price should be {old_price}, got {price_drop_info.get('old_price_usd')}"
            )
        else:
            assert price_drop_info is None, (
                f"No price drop from {old_price} to {new_price} should be detected, "
                f"but got {price_drop_info}"
            )
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    old_price_jpy=st.integers(min_value=1000, max_value=100000),
    new_price_jpy=st.integers(min_value=100, max_value=99999),
)
def test_price_drop_detection_mercari_full_history(old_price_jpy, new_price_jpy):
    """
    Feature: amazon-scraper-refactor
    Property 11: Price Drop Notification in Full-History Mode (Mercari variant)
    Validates: Requirements 9.4
    
    For any Mercari price update in full_history mode where new_price < old_price,
    the system SHALL detect a price drop.
    """
    # Ensure we have distinct prices for meaningful test
    assume(old_price_jpy != new_price_jpy)
    
    # Create a temporary database for isolation
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_products.db")
    
    try:
        storage = ProductStorage(db_path=db_path)
        source = "mercari_jp"
        product_id = "m1234567890"
        
        # Create initial product with old price
        initial_product = {
            "id": product_id,
            "title": "Test Mercari Product",
            "price_jpy": old_price_jpy,
            "price_twd": old_price_jpy // 5,
            "product_url": f"https://jp.mercari.com/item/{product_id}",
        }
        
        # Insert initial product and record price history
        storage.upsert_product(initial_product, source, tracking_mode="full_history")
        
        # Create updated product with new price
        updated_product = {
            "id": product_id,
            "title": "Test Mercari Product",
            "price_jpy": new_price_jpy,
            "price_twd": new_price_jpy // 5,
            "product_url": f"https://jp.mercari.com/item/{product_id}",
        }
        
        # Detect price drop before upserting
        price_drop_info = storage.detect_price_drop(updated_product, source, tracking_mode="full_history")
        
        # Property: price drop detected if and only if new_price < old_price
        is_price_drop = new_price_jpy < old_price_jpy
        
        if is_price_drop:
            assert price_drop_info is not None, (
                f"Price drop from {old_price_jpy} to {new_price_jpy} should be detected"
            )
            assert price_drop_info.get("old_price_jpy") == old_price_jpy, (
                f"Old price should be {old_price_jpy}, got {price_drop_info.get('old_price_jpy')}"
            )
        else:
            assert price_drop_info is None, (
                f"No price drop from {old_price_jpy} to {new_price_jpy} should be detected, "
                f"but got {price_drop_info}"
            )
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    prices=st.lists(
        st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=10
    )
)
def test_price_history_accumulation_full_history(prices):
    """
    Feature: amazon-scraper-refactor
    Property 11: Price Drop Notification in Full-History Mode (history accumulation)
    Validates: Requirements 9.4
    
    For any sequence of N price updates in full_history mode,
    the price_history table SHALL contain exactly N records,
    and price drops SHALL be detected correctly against the most recent price.
    """
    # Round prices for consistency
    prices = [round(p, 2) for p in prices]
    
    # Create a temporary database for isolation
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_products.db")
    
    try:
        storage = ProductStorage(db_path=db_path)
        source = "amazon_us"
        product_id = "B0123456789"
        
        detected_drops = []
        
        for i, price in enumerate(prices):
            product = {
                "id": product_id,
                "title": "Test Amazon Product",
                "price_usd": price,
                "product_url": f"https://www.amazon.com/dp/{product_id}",
            }
            
            if i > 0:
                # Check for price drop before upserting
                price_drop_info = storage.detect_price_drop(product, source, tracking_mode="full_history")
                
                # Property: price drop detected if new price < previous price
                previous_price = prices[i - 1]
                is_price_drop = price < previous_price
                
                if is_price_drop:
                    assert price_drop_info is not None, (
                        f"Price drop from {previous_price} to {price} should be detected"
                    )
                    detected_drops.append((previous_price, price))
                else:
                    assert price_drop_info is None, (
                        f"No price drop from {previous_price} to {price} should be detected"
                    )
            
            # Upsert the product
            storage.upsert_product(product, source, tracking_mode="full_history")
        
        # Verify price history count
        history_count = storage.get_price_history_count(product_id, source)
        assert history_count == len(prices), (
            f"Expected {len(prices)} price history records, got {history_count}"
        )
        
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    old_price=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    new_price=st.floats(min_value=1.0, max_value=999.0, allow_nan=False, allow_infinity=False),
)
def test_compare_products_triggers_price_drop_full_history(old_price, new_price):
    """
    Feature: amazon-scraper-refactor
    Property 11: Price Drop Notification in Full-History Mode (via compare_products)
    Validates: Requirements 9.4
    
    For any price update via compare_products in full_history mode,
    price drops SHALL be included in the result's price_dropped list.
    """
    old_price = round(old_price, 2)
    new_price = round(new_price, 2)
    assume(old_price != new_price)
    
    # Create a temporary database for isolation
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_products.db")
    
    try:
        storage = ProductStorage(db_path=db_path)
        source = "amazon_us"
        product_id = "B0123456789"
        
        # Create and insert initial product
        initial_product = {
            "id": product_id,
            "title": "Test Amazon Product",
            "price_usd": old_price,
            "product_url": f"https://www.amazon.com/dp/{product_id}",
        }
        storage.upsert_product(initial_product, source, tracking_mode="full_history")
        
        # Create updated product with new price
        updated_product = {
            "id": product_id,
            "title": "Test Amazon Product",
            "price_usd": new_price,
            "product_url": f"https://www.amazon.com/dp/{product_id}",
        }
        
        # Use compare_products to detect changes
        result = storage.compare_products([updated_product], source, tracking_mode="full_history")
        
        # Property: price drop in result if and only if new_price < old_price
        is_price_drop = new_price < old_price
        
        if is_price_drop:
            assert len(result["price_dropped"]) == 1, (
                f"Expected 1 price drop, got {len(result['price_dropped'])}"
            )
            assert result["price_dropped"][0].get("old_price_usd") == old_price, (
                f"Old price should be {old_price}"
            )
        else:
            assert len(result["price_dropped"]) == 0, (
                f"Expected no price drops, got {len(result['price_dropped'])}"
            )
        
        # New products list should be empty (product already exists)
        assert len(result["new"]) == 0, (
            f"Expected no new products, got {len(result['new'])}"
        )
        
    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
