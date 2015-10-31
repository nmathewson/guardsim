#!/usr/bin/python

_time = 0

def now():
    return _time

def advanceTime(n):
    global _time
    assert n >= 0
    _time += n
