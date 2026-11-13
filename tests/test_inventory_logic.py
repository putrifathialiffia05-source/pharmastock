from datetime import date, timedelta
from services.inventory_logic import (
    calculate_safety_stock,
    calculate_min_stock,
    calculate_max_stock,
    get_inventory_status,
    get_expiry_status,
    sort_fefo_batches,
)


def test_safety_stock_calculation():
    # ADC = 10 units/day, Buffer = 5 days -> 50 units
    assert calculate_safety_stock(10.0, 5) == 50
    # ADC with fractional demand should round up
    assert calculate_safety_stock(7.2, 3) == 22  # 7.2 * 3 = 21.6 -> 22
    # Edge case: zero or negative values
    assert calculate_safety_stock(0, 5) == 0
    assert calculate_safety_stock(10, -2) == 0


def test_min_stock_reorder_point():
    # ADC = 15, Lead Time = 7 days, Safety Stock = 50
    # Lead time demand = 105, Min Stock = 105 + 50 = 155
    assert calculate_min_stock(15.0, 7, 50) == 155
    # Fractional handling
    assert calculate_min_stock(3.3, 5, 20) == 37  # 3.3 * 5 = 16.5 + 20 = 36.5 -> 37


def test_max_stock_calculation():
    # Min Stock = 155, ADC = 15, Review Cycle = 14 days
    # Cycle demand = 15 * 14 = 210 -> Max Stock = 155 + 210 = 365
    assert calculate_max_stock(155, 15.0, 14) == 365


def test_inventory_status_classification():
    min_stock = 100
    max_stock = 300

    assert get_inventory_status(0, min_stock, max_stock) == 'OUT_OF_STOCK'
    assert get_inventory_status(40, min_stock, max_stock) == 'CRITICAL_LOW'  # <= 50% of 100
    assert get_inventory_status(85, min_stock, max_stock) == 'LOW_STOCK'      # <= 100
    assert get_inventory_status(200, min_stock, max_stock) == 'NORMAL'       # between min and max
    assert get_inventory_status(350, min_stock, max_stock) == 'OVERSTOCKED'  # > 300


def test_expiry_status_classification():
    today = date.today()

    # Expired
    past_date = today - timedelta(days=5)
    status, days = get_expiry_status(past_date, today)
    assert status == 'EXPIRED'
    assert days == -5

    # Critical (< 30 days)
    critical_date = today + timedelta(days=20)
    status, days = get_expiry_status(critical_date, today)
    assert status == 'CRITICAL'
    assert days == 20

    # Warning (31 - 90 days)
    warning_date = today + timedelta(days=60)
    status, days = get_expiry_status(warning_date, today)
    assert status == 'WARNING'
    assert days == 60

    # Good (> 90 days)
    good_date = today + timedelta(days=180)
    status, days = get_expiry_status(good_date, today)
    assert status == 'GOOD'
    assert days == 180


def test_fefo_sorting():
    class DummyBatch:
        def __init__(self, name, qty, expiry_date):
            self.name = name
            self.quantity = qty
            self.expiry_date = expiry_date

    today = date.today()
    batch_a = DummyBatch('Batch A (Expires in 60d)', 10, today + timedelta(days=60))
    batch_b = DummyBatch('Batch B (Expires in 15d)', 25, today + timedelta(days=15))
    batch_c = DummyBatch('Batch C (Expires in 120d)', 50, today + timedelta(days=120))
    batch_empty = DummyBatch('Batch D (Empty)', 0, today + timedelta(days=5))

    batches = [batch_a, batch_c, batch_empty, batch_b]
    sorted_batches = sort_fefo_batches(batches)

    # Empty batch should be excluded; batch_b (15d) should be first, then batch_a (60d), then batch_c (120d)
    assert len(sorted_batches) == 3
    assert sorted_batches[0].name == 'Batch B (Expires in 15d)'
    assert sorted_batches[1].name == 'Batch A (Expires in 60d)'
    assert sorted_batches[2].name == 'Batch C (Expires in 120d)'
