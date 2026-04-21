"""Universe-wide scanner framework (parallel to per-candle Strategy framework).

Scanners run on a schedule, iterate the full NSE/BSE universe, and emit
``ScanCandidate`` rows that users promote into orders via ApprovalService.
"""
