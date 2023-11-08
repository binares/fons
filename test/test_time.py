import pytest
import datetime

dt = datetime.datetime
td = datetime.timedelta
import pandas as pd

ofs = pd.tseries.offsets

import fons.time as time


params = [
    [dt(2000, 2, 13, 4, 3), td(30), 0, dt(2000, 2, 1)],
    [dt(2000, 2, 13, 4, 3), "1MS", 0, dt(2000, 2, 1)],
    [dt(2000, 2, 13, 4, 3), "30D", 0, dt(2000, 2, 1)],
    [dt(2000, 2, 13, 4, 3), ofs.MonthBegin(), 0, dt(2000, 2, 1)],
    [dt(2000, 2, 13, 4, 3), ofs.Day(30), 0, dt(2000, 2, 1)],
]

params2 = [[dt(2000, 2, 1)] + x[1:] for x in params]
# params += params2

# Some tests have base > 0 or ofs.X(n,True)
# the first should only affect frequencies < td(1)
# the latter should affect nothing

params3 = [
    [dt(1996, 2, 29, 10), "BH", 0, dt(1996, 2, 29, 10)],
    [dt(1996, 2, 29, 10, 2), "BH", 0, dt(1996, 2, 29, 10)],
    [dt(1996, 2, 26, 6, 2), ofs.BusinessHour(1), 0, dt(1996, 2, 23, 16, 0)],
    [dt(1996, 2, 26, 6, 2), "B", 0, dt(1996, 2, 26, 0, 0)],
    [dt(1996, 2, 25, 6, 2), "B", 0, dt(1996, 2, 23, 0, 0)],
    [dt(1996, 2, 26, 6, 2), ofs.BusinessDay(1, True), 0, dt(1996, 2, 26, 0, 0)],
]

params4 = [
    [dt(2000, 2, 13, 4, 3), "28D", 0, dt(2000, 2, 13)],
    [dt(2000, 2, 13, 4, 3), td(2), 0, dt(2000, 2, 13)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(25), 0, dt(2000, 2, 13)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(23), 0, dt(2000, 2, 13, 23)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(23), 1, dt(2000, 2, 13, 1)],
    # [dt(2000,2,13,23,3),ofs.Hour(23,True),1,dt(2000,2,13,1)],
    [dt(2000, 2, 13, 23, 3), "5T", 0, dt(2000, 2, 13, 23, 0)],
    [dt(2000, 2, 13, 23, 3), td(minutes=5), 2, dt(2000, 2, 13, 23, 2)],
    [dt(1996, 1, 2), "3W", 0, dt(1996, 1, 7)],
    [dt(1996, 1, 7, 2), "3W", 0, dt(1996, 1, 7)],
    [dt(2000, 2, 13, 4, 3), ofs.MonthEnd(1), 0, dt(2000, 2, 29)],
    [dt(2000, 2, 1), "1M", 0, dt(2000, 2, 29)],
    [dt(2000, 1, 31, 2), "1M", 0, dt(2000, 1, 31)],  # dt(2000,2,29)],
    [dt(2000, 1, 31, 0), "1M", 0, dt(2000, 1, 31)],
    [dt(2000, 2, 1), td(366), 0, dt(2000, 1, 1)],
    [dt(2000, 2, 1), "Y", 0, dt(2000, 12, 31)],
]

params += params2 + params3 + params4


@pytest.mark.parametrize("date,freq,base,expected", params)
def test_dt_round(date, freq, base, expected):
    assert time.dt_round(date, freq, base) == expected


normalized = [x[:-1] + [time.dt_round_to_digit(x[-1], td(1))] for x in params]


@pytest.mark.parametrize("date,freq,base,expected", normalized)
def test_dt_round_normalized(date, freq, base, expected):
    assert time.dt_round(date, freq, base, normalize=True) == expected


negative = [
    [dt(2000, 2, 13, 4, 3), -td(30), 0, dt(2000, 3, 1)],
    [dt(2000, 2, 13, 4, 3), "-1MS", 0, dt(2000, 3, 1)],
    [dt(2000, 2, 13, 4, 3), "-30D", 0, dt(2000, 3, 1)],
    [dt(2000, 2, 13, 4, 3), ofs.MonthBegin(-1), 0, dt(2000, 3, 1)],
    [dt(2000, 2, 13, 4, 3), ofs.Day(-30), 0, dt(2000, 3, 1)],
]

negative2 = [[dt(2000, 3, 1)] + x[1:] for x in negative]

negative3 = [
    [dt(1996, 2, 29, 10), "-1BH", 0, dt(1996, 2, 29, 10)],
    [dt(1996, 2, 29, 10, 2), "-1BH", 0, dt(1996, 2, 29, 11)],
    [dt(1996, 2, 26, 6, 2), ofs.BusinessHour(-1), 0, dt(1996, 2, 26, 9)],
    [dt(1996, 2, 26, 6, 2), "-1B", 0, dt(1996, 2, 27)],
    [dt(1996, 2, 25, 6, 2), "-1B", 0, dt(1996, 2, 26)],
    [dt(1996, 2, 26, 6, 2), ofs.BusinessDay(-1, True), 0, dt(1996, 2, 27)],
]

negative4 = [
    [dt(2000, 2, 13, 4, 3), "-28D", 0, dt(2000, 2, 14)],
    [dt(2000, 2, 13, 4, 3), td(-2), 0, dt(2000, 2, 14)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(-25), 0, dt(2000, 2, 14)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(-23), 0, dt(2000, 2, 14, 0)],
    [dt(2000, 2, 13, 23, 3), ofs.Hour(-23), 1, dt(2000, 2, 14, 22)],
    # [dt(2000,2,13,23,3),ofs.Hour(-23,True),1,dt(2000,2,14,22)] , #Ticks don't allow `normalize` since pandas 0.25
    [dt(2000, 2, 13, 23, 3), "-5T", 0, dt(2000, 2, 13, 23, 5)],
    [dt(2000, 2, 13, 23, 3), td(minutes=-5), 2, dt(2000, 2, 13, 23, 3)],
    [dt(1996, 1, 2), "-1W", 0, dt(1995, 12, 31)],
    [dt(1996, 1, 7, 2), "-1W", 0, dt(1996, 1, 7)],
    [dt(2000, 2, 13, 4, 3), ofs.MonthEnd(-1), 0, dt(2000, 1, 31)],
    [dt(2000, 2, 1), "-1M", 0, dt(2000, 1, 31)],
    [dt(2000, 1, 31, 2), "-1M", 0, dt(2000, 1, 31)],  # dt(2000,2,29)],
    [dt(2000, 1, 31, 0), "-1M", 0, dt(2000, 1, 31)],
    [dt(2000, 2, 1), td(-366), 0, dt(2001, 1, 1)],
    [dt(2000, 2, 1), "-1Y", 0, dt(1999, 12, 31)],
]

negative += negative2 + negative3 + negative4


@pytest.mark.parametrize("date,freq,base,expected", negative)
def test_dt_round_negative(date, freq, base, expected):
    assert time.dt_round(date, freq, base) == expected
