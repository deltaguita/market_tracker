#!/usr/bin/env python3
"""
Property-based test for Max Threshold Filtering

Feature: amazon-scraper-refactor
Property 13: Max Threshold Filtering
Validates: Requirements 8.3

*For any* Amazon product with price P and config with `max_usd` = M,
the product SHALL be included in notifications if and only if P <= M.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hypothesis import given, strategies as st, settings
from main import filter_products_by_threshold, filter_price_dropped_by_threshold


# Strategies for generating test data
price_strategy = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
threshold_strategy = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)


@st.composite
def amazon_product_strategy(draw):
    """Generate a random Amazon product with USD price"""
    price = draw(price_strategy)
    return {
        "id": f"B{draw(st.text(alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=9, max_size=9))}",
        "title": draw(st.text(min_size=1, max_size=100)),
        "price_usd": round(price, 2),
        "product_url": f"https://www.amazon.com/dp/B{draw(st.text(alphabet='0123456789', min_size=9, max_size=9))}",
    }


@st.composite
def mercari_product_strategy(draw):
    """Generate a random Mercari product with TWD price"""
    price = draw(st.integers(min_value=1, max_value=100000))
    return {
        "id": f"m{draw(st.text(alphabet='0123456789', min_size=10, max_size=10))}",
        "title": draw(st.text(min_size=1, max_size=100)),
        "price_twd": price,
        "price_jpy": price * 5,  # Approximate conversion
        "product_url": f"https://jp.mercari.com/item/m{draw(st.text(alphabet='0123456789', min_size=10, max_size=10))}",
    }


@settings(max_examples=100)
@given(
    products=st.lists(amazon_product_strategy(), min_size=0, max_size=20),
    max_threshold=threshold_strategy
)
def test_max_threshold_filtering_amazon_inclusion(products, max_threshold):
    """
    Feature: amazon-scraper-refactor
    Property 13: Max Threshold Filtering
    Validates: Requirements 8.3
    
    For any Amazon product with price P and max_usd = M,
    the product is included if and only if P <= M.
    """
    filtered = filter_products_by_threshold(products, max_threshold, "amazon_us")
    
    for product in products:
        price = product.get("price_usd", 0)
        is_included = product in filtered
        should_be_included = price > 0 and price <= max_threshold
        
        assert is_included == should_be_included, (
            f"Product with price {price} and threshold {max_threshold}: "
            f"included={is_included}, should_be_included={should_be_included}"
        )


@settings(max_examples=100)
@given(
    products=st.lists(amazon_product_strategy(), min_size=0, max_size=20),
)
def test_no_threshold_includes_all_amazon(products):
    """
    Feature: amazon-scraper-refactor
    Property 13: Max Threshold Filtering (no threshold case)
    Validates: Requirements 8.3
    
    When max_threshold is None, all products should be included.
    """
    filtered = filter_products_by_threshold(products, None, "amazon_us")
    assert filtered == products


@settings(max_examples=100)
@given(
    products=st.lists(mercari_product_strategy(), min_size=0, max_size=20),
    max_threshold=st.integers(min_value=1, max_value=100000)
)
def test_max_threshold_filtering_mercari_inclusion(products, max_threshold):
    """
    Feature: amazon-scraper-refactor
    Property 13: Max Threshold Filtering (Mercari variant)
    Validates: Requirements 8.4
    
    For any Mercari product with price P (TWD) and max_ntd = M,
    the product is included if and only if P <= M.
    """
    filtered = filter_products_by_threshold(products, max_threshold, "mercari_jp")
    
    for product in products:
        price = product.get("price_twd", 0)
        is_included = product in filtered
        should_be_included = price > 0 and price <= max_threshold
        
        assert is_included == should_be_included, (
            f"Product with price {price} and threshold {max_threshold}: "
            f"included={is_included}, should_be_included={should_be_included}"
        )


@settings(max_examples=100)
@given(
    price_dropped=st.lists(
        st.fixed_dictionaries({
            "product": amazon_product_strategy(),
            "old_price_usd": price_strategy,
        }),
        min_size=0,
        max_size=20
    ),
    max_threshold=threshold_strategy
)
def test_price_dropped_threshold_filtering_amazon(price_dropped, max_threshold):
    """
    Feature: amazon-scraper-refactor
    Property 13: Max Threshold Filtering (price dropped items)
    Validates: Requirements 8.3
    
    For any price dropped item with current price P and max_usd = M,
    the item is included if and only if P <= M.
    """
    filtered = filter_price_dropped_by_threshold(price_dropped, max_threshold, "amazon_us")
    
    for item in price_dropped:
        price = item["product"].get("price_usd", 0)
        is_included = item in filtered
        should_be_included = price > 0 and price <= max_threshold
        
        assert is_included == should_be_included, (
            f"Price dropped item with price {price} and threshold {max_threshold}: "
            f"included={is_included}, should_be_included={should_be_included}"
        )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
