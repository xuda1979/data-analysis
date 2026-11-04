"""P4 controllers (plan §5 H1/H2): forecasts, hold/trade thresholds, budgets.

H1/H2 controllers live here and share the frozen forecast module
(`forecasts.py`); H3 is P5. All controllers use only data at indices <= i.
"""
