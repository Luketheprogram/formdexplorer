"""Regular SEC federal closures; exceptional closures stay visible for review.

Source: https://www.sec.gov/submit-filings/filer-support-resources/edgar-calendar
An expected closure only excuses HTTP 404. Any published index is still ingested.
"""
from datetime import date, timedelta
from functools import lru_cache


def observed(day):
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


@lru_cache(maxsize=128)
def closures(year):
    result = set()
    for y in (year, year + 1):
        for month, day in ((1, 1), (7, 4), (11, 11), (12, 25)):
            result.add(observed(date(y, month, day)))
        if y >= 2021:
            result.add(observed(date(y, 6, 19)))
    for month, weekday, n in ((1, 0, 3), (2, 0, 3), (9, 0, 1), (10, 0, 2), (11, 3, 4)):
        result.add(nth_weekday(year, month, weekday, n))
    # Last Monday in May.
    last = date(year, 5, 31)
    result.add(last - timedelta(days=last.weekday()))
    return result


def expected_closure(day):
    return day.weekday() >= 5 or day in closures(day.year)
