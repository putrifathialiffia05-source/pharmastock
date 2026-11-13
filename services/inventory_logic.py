"""
PharmaStock - Pharmacy Inventory Calculations & Rules Engine

This module encapsulates core pharmaceutical inventory formulas:
1. Average Daily Consumption (ADC)
2. Safety Stock (SS)
3. Minimum Stock Level / Reorder Point (ROP)
4. Maximum Stock Level (Max)
5. Expiry Status & First-Expired, First-Out (FEFO) prioritization
"""

import math
from datetime import date


def calculate_safety_stock(avg_daily_consumption: float, safety_stock_days: int) -> int:
    """
    Calculate the Safety Stock (Buffer Stock).
    Formula: Safety Stock = ADC * Safety Stock Days
    
    Purpose in Pharmacy:
    Prevents stockouts caused by unexpected demand surges (e.g. seasonal flu outbreaks)
    or supplier shipment delays.
    """
    if avg_daily_consumption <= 0 or safety_stock_days <= 0:
        return 0
    return math.ceil(avg_daily_consumption * safety_stock_days)


def calculate_min_stock(avg_daily_consumption: float, lead_time_days: int, safety_stock: int) -> int:
    """
    Calculate Minimum Stock Level / Reorder Point (ROP).
    Formula: Min Stock = (ADC * Lead Time) + Safety Stock
    
    Purpose in Pharmacy:
    The threshold inventory level that triggers a purchase order. When stock reaches
    this number, ordering immediately ensures the new shipment arrives just as safety
    stock is touched.
    """
    lead_time_demand = avg_daily_consumption * max(0, lead_time_days)
    return math.ceil(lead_time_demand + max(0, safety_stock))


def calculate_max_stock(min_stock: int, avg_daily_consumption: float, review_cycle_days: int = 14) -> int:
    """
    Calculate Maximum Stock Level.
    Formula: Max Stock = Min Stock + (ADC * Review Cycle Days)
    
    Purpose in Pharmacy:
    The ceiling for warehouse or dispensary capacity. Exceeding this ties up hospital/clinic
    capital unnecessarily and dramatically increases the risk of drugs reaching expiration
    before being dispensed.
    """
    cycle_demand = avg_daily_consumption * max(0, review_cycle_days)
    return math.ceil(min_stock + cycle_demand)


def get_inventory_status(current_stock: int, min_stock: int, max_stock: int) -> str:
    """
    Classify the stock level into standardized inventory states:
    - OUT_OF_STOCK: 0 units available
    - CRITICAL_LOW: Stock is <= 50% of the minimum threshold
    - LOW_STOCK: Stock is <= minimum threshold (Needs reorder)
    - OVERSTOCKED: Stock exceeds the maximum storage ceiling
    - NORMAL: Stock is within safe operating range
    """
    if current_stock <= 0:
        return 'OUT_OF_STOCK'
    if min_stock > 0 and current_stock <= (min_stock * 0.5):
        return 'CRITICAL_LOW'
    if current_stock <= min_stock:
        return 'LOW_STOCK'
    if max_stock > 0 and current_stock > max_stock:
        return 'OVERSTOCKED'
    return 'NORMAL'


def get_expiry_status(expiry_date: date, reference_date: date = None) -> tuple[str, int]:
    """
    Evaluate the expiry status of a drug batch relative to a reference date.
    Returns (status_label, days_remaining).
    
    Status definitions:
    - EXPIRED: Already passed expiration date (Quarantine immediately!)
    - CRITICAL: Expires within 30 days (High alert, priority dispensing or return to vendor)
    - WARNING: Expires within 90 days (Place in front for FEFO dispensing)
    - GOOD: More than 90 days remaining shelf life
    """
    if reference_date is None:
        reference_date = date.today()

    days_remaining = (expiry_date - reference_date).days

    if days_remaining <= 0:
        return 'EXPIRED', days_remaining
    elif days_remaining <= 30:
        return 'CRITICAL', days_remaining
    elif days_remaining <= 90:
        return 'WARNING', days_remaining
    else:
        return 'GOOD', days_remaining


def sort_fefo_batches(batches: list) -> list:
    """
    First-Expired, First-Out (FEFO) sorting.
    Returns batches ordered by earliest expiration date first.
    Filters out empty batches (quantity == 0).
    """
    active_batches = [b for b in batches if getattr(b, 'quantity', 0) > 0]
    return sorted(active_batches, key=lambda b: getattr(b, 'expiry_date'))
