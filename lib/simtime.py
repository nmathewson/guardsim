#!/usr/bin/python

"""Stupid simulated global time code."""

_time = 0

def now():
    """Return the current simulated time."""
    return _time

def advanceTime(n):
    """Advance the current simulated time by X seconds."""
    global _time
    assert n >= 0
    _time += n
