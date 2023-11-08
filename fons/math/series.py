import pandas as pd
import numpy as np
import datetime

dt = datetime.datetime
td = datetime.timedelta

from fons.time import freq_to_offset, dt_round


_unitTD = {"_type_": td, "_call_": None}
_unitDT = {"_type_": dt, "_call_": None}
_multiunit = {"_multi_": [_unitTD, _unitDT]}

TP_TYPES = {
    "_defval_": {"_type_": type(None), "_value_": None},
    "_multi_": [
        {"_type_": tuple, "unit": _multiunit, "_call_": None},
        {"_type_": list, "unit": _multiunit, "_call_": None},
        _unitTD,
        _unitDT,
    ],
}


# pd.tslib.Timedelta is ok with both np.datetime64/np.timedelta64 & dt/td
# np.datetime64/np.timedelta64 & dt/td don't match


def _check_none_borders(borders):
    if borders is None:
        return True

    elif not isinstance(borders, (list, tuple, np.ndarray)):
        return False

    if not len(borders):
        return True
    elif all(x is None for x in borders):
        return True

    return False


def get_timestamps(time_period, return_fmt=None):
    tp = time_period
    end = pd.to_datetime(dt.utcnow())

    if tp is None:
        return None

    if not isinstance(tp, (tuple, list, np.ndarray)):
        tp = (tp, end)

    ln = len(tp)
    if ln > 2:
        raise ValueError(time_period, "size > 2")
    elif not ln or all(x is None for x in tp):
        return None
    elif ln == 1:
        tp = (tp[0], end)

    tp = tuple(
        x
        if x is None
        else (
            pd.to_datetime(x)
            if isinstance(x, (dt, np.datetime64))
            else freq_to_offset(x)
        )
        for x in tp
    )
    dtypes = tuple(x if x is None else ("t" if isinstance(x, dt) else "d") for x in tp)
    # print(tp,dtypes)

    if dtypes == ("d", None):
        begin = end - tp[0]
        end = None

    elif dtypes == (None, "d"):
        begin = None
        end -= tp[1]

    elif dtypes == ("t", "d"):
        begin = tp[0]
        end = begin + tp[1]

    elif dtypes == ("d", "t"):
        end = tp[1]
        begin = end - tp[0]

    elif dtypes == ("d", "d"):
        end -= tp[1]
        begin = end - tp[0]

    else:
        begin = tp[0]
        end = tp[1]

    timestamps = (begin, end)

    if return_fmt == "np.datetime64":
        # converts both dt and pandas Timestamp
        timestamps = tuple(np.datetime64(x) if x is not None else x for x in timestamps)
    elif return_fmt == "pydatetime":
        timestamps = tuple(
            x.to_pydatetime() if x is not None else x for x in timestamps
        )

    return timestamps


def get_period_entries(
    start,
    end,
    nr_periods=None,
    freq="D",
    round_start=False,
    exclude_end=False,
    exclude_noncomplete=False,
    return_as="DatetimeIndex",
):
    dtrange = None
    if not isinstance(freq, td):
        dtrange = pd.date_range(start, end, periods=nr_periods, freq=freq)
        freq = dtrange.freq._offset * dtrange.freq.n

    if round_start:
        start = dt_round(start, freq)
        dtrange = pd.date_range(start, end, periods=nr_periods, freq=freq)

    if dtrange is None:
        dtrange = pd.date_range(start, end, periods=nr_periods, freq=freq)

    if end is not None and exclude_end:
        if dtrange[-1] >= end:
            dtrange = dtrange[:-1]

        # excludes the last period if it is not "complete"
        if exclude_noncomplete and dtrange.shape[0]:
            if dtrange[-1] + freq > end:
                dtrange = dtrange[:-1]

    if return_as == "DatetimeIndex":
        return dtrange
    elif return_as == "PeriodIndex":
        return dtrange.to_period(freq)
    elif return_as in ("pydatetime", "datetime.datetime", "dt.datetime"):
        return dtrange.to_pydatetime()
    else:
        raise ValueError(return_as)


def format_ts(ts, strfformat, nr_microsecs=None):
    # print(ts,strfformat)
    if isinstance(strfformat, dict):
        strftime = ts.strftime(strfformat["strf"])
        nr_microsecs = strfformat.get("nr_microsecs")

    else:
        strftime = ts.strftime(strfformat)

    if "%f" in strfformat and nr_microsecs and nr_microsecs < 6:
        strftime = strftime[: (-6 + nr_microsecs)]

    return strftime


# time period or just a single timestamp
def format_tp(tp, strfformat, nr_microsecs=None):
    timestamps = get_timestamps(tp)

    strftimes = [format_ts(ts, strfformat, nr_microsecs) for ts in timestamps]

    timedeltas = [
        td(days=365),
        td(days=30),
        td(days=1),
        td(hours=1),
        td(minutes=1),
        td(seconds=1),
        td(milliseconds=1),
        td(microseconds=1),
    ]
    delta = timestamps[1] - timestamps[0]

    if delta in timedeltas:
        return strftimes[0]
    else:
        return "to".join(strftimes)


def get_fringe_entries(obj, key=None, func=None):
    key_isfunc = hasattr(key, "__call__")
    entries = []
    key0 = key

    if isinstance(obj, (pd.DataFrame, pd.Series)):
        if isinstance(obj, pd.DataFrame):
            if key is not None:
                _iterable = obj[key] if not key_isfunc else key(obj)
            else:
                _iterable = obj.index

        elif isinstance(obj, pd.Series):
            if key_isfunc:
                _iterable = key(obj)
            elif obj.dtypes.name == "datetime64[ns]":
                _iterable = obj
            else:
                _iterable = obj.index

        try:
            if isinstance(_iterable, pd.Series):
                entries = [_iterable.iloc[0], _iterable.iloc[-1]]
            else:
                entries = [_iterable[0], _iterable[-1]]
        except IndexError:
            pass

    else:
        try:
            hasgetitem = hasattr(obj[0], "__getitem__")
        except IndexError:
            hasgetitem = False

        if key is None:
            key = lambda x: x
        elif key_isfunc:
            pass
        elif hasgetitem:
            key = lambda x: x[key0]
        else:
            key = lambda x: getattr(x, key)

        try:
            entries = [key(obj[0]), key(obj[-1])]
        except IndexError:
            pass

    if func:
        entries = [func(x) for x in entries]

    return entries


def _apply_key_func(obj, key=None, func=None):
    key_isfunc = hasattr(key, "__call__")
    is_gen = False

    if isinstance(obj, pd.DataFrame):
        if key is not None:
            _iterable = obj[key] if not key_isfunc else key(obj)
        else:
            _iterable = obj.index

    elif isinstance(obj, pd.Series):
        if key_isfunc:
            _iterable = key(obj)
        elif obj.dtypes.name == "datetime64[ns]":
            _iterable = obj
        else:
            _iterable = obj.index

    else:
        try:
            hasgetitem = hasattr(obj[0], "__getitem__")
        except IndexError:
            hasgetitem = False

        if key is None:
            _iterable = obj
        elif key_isfunc:
            _iterable, is_gen = map(key, obj), True
        elif hasgetitem:
            _iterable, is_gen = map(lambda x: x[key], obj), True
        else:
            _iterable, is_gen = map(lambda x: getattr(x, key), obj), True

    if not func:
        pass
    elif isinstance(_iterable, (pd.Series, pd.Index)):
        _iterable = _iterable.apply(func)
    else:
        _iterable, is_gen = map(func, _iterable), True

    return _iterable, is_gen


def get_time_borders(obj, tp, key=None):
    tp = get_timestamps(tp, "pd.Timestamp")
    # temporary, due to supposed 0.21 pandas bug
    # tp = get_timestamps(tp,'pydatetime')
    if tp is None:
        return None

    begin, end = tp
    start, finish = None, None

    _iterable, is_gen = _apply_key_func(obj, key)

    # temporary:
    if isinstance(_iterable, np.ndarray):
        tp = tuple([np.datetime64(x) for x in tp])

    if isinstance(_iterable, (pd.Series, pd.DatetimeIndex, np.ndarray)):
        b_array = (_iterable >= begin) & (_iterable < end)
        indexes = b_array.nonzero()[0]

        if indexes.shape[0]:
            start = indexes[0]
            finish = indexes[-1]

    else:
        for i, ts in enumerate(_iterable):
            if start is None and ts >= begin:
                start = i

            if ts < end:
                finish = i
            else:
                break

    if None in (start, finish):
        return None

    return (start, finish)


def get_slice_where(obj, borders, key=None, func=None):
    borders = get_timestamps(borders, return_fmt="pd.Timestamp")
    if borders is None:
        return np.arange(0)
    elif borders is False:
        return np.arange(0)
    elif not len(obj):
        return np.arange(0)

    begin, end = borders
    _iterable, is_gen = _apply_key_func(obj, key, func)

    if not isinstance(_iterable, (pd.Series, pd.Index, np.ndarray)):
        if is_gen:
            _iterable = tuple(_iterable)
        _iterable = np.asarray(_iterable)

    # seems to be necessary (py 3.6, pd 0.22, np 1.14), even if tp consists of pd.TimeStamps
    if isinstance(_iterable, np.ndarray):
        begin, end = [np.datetime64(x) if x is not None else None for x in borders]

    if not begin:
        b_array = _iterable < end
    elif not end:
        b_array = _iterable >= begin
    else:
        b_array = (_iterable >= begin) & (_iterable < end)

    return b_array


def get_slice_indexes(obj, borders, key=None, func=None):
    b_array = get_slice_where(obj, borders, key=key, func=func)
    indexes = b_array.nonzero()[0]
    # the indexes are absolute (iloc), not related to the actual index (of pd.Series)

    return indexes


def slice_obj(obj, tp, key=None, func=None):
    if _check_none_borders(tp):
        return obj
    where = get_slice_where(obj, tp, key, func)

    if not where.any():
        obj2 = obj[-1:-1]

    elif isinstance(obj, (pd.DataFrame, pd.Series)):
        # if DataFrame without using loc, boolean is automatically applied to index
        # (other types like int/str.. are applied to columns)
        obj2 = obj[where]
    else:
        try:
            obj2 = obj[where]
        except TypeError:
            _type = type(obj)
            obj2 = _type((x for x, b in zip(obj, where) if b))

    return obj2


#############################
def _get_last_nonnan(a):
    nonnan = a[~np.isnan(a)]
    if nonnan.shape[0]:
        return nonnan[-1]
    return np.nan


def _implement_fill_policy(a, how="previous", fill_remaining=True, if_all="leave", r=0):
    s = a
    if not isinstance(a, pd.Series):
        s = pd.Series(a)

    if how in ("next", 1):
        s = s[::-1]

    sp = s.rolling(window=s.shape[0], min_periods=1).agg(_get_last_nonnan)
    # print(sp,if_all)

    if not sp.isnull().any():
        pass
    elif sp.isnull().all() and if_all == "drop":
        sp.dropna(inplace=True)
    elif fill_remaining and r == 0:
        sp = _implement_fill_policy(sp, "next", fill_remaining, if_all, r=r + 1)

    if how in ("next", 1):
        sp = sp[::-1]

    # sp2 is copy, does not affect s
    return sp


def implement_nan_policy(a, how="drop", **kw):
    def_policy = {"how": "drop", "fill_remaining": False, "if_all": "drop"}
    policy = _nan_policy_vars(how, dict(def_policy, **kw))
    how = policy["how"]

    s = a
    if not isinstance(a, pd.Series):
        s = pd.Series(a)

    s2 = s

    if not s.isnull().any() or how == "leave":
        pass
    elif how == "drop":
        s2 = s.dropna()
    elif how in ("previous", "prev", "next", -1, 1):
        s2 = _implement_fill_policy(s, **policy)

    return s2.values


def _nan_policy_vars(policy, def_vals):
    policy2 = def_vals.copy()
    k = ("how", "fill_remaining", "if_all")

    if isinstance(policy, (list, tuple)):
        for p, v in zip(k, policy):
            policy2[p] = v
    elif isinstance(policy, dict):
        policy2.update(policy)
    elif policy is not None:
        policy2[k[0]] = policy

    return policy2


def undo_cumsum(_iterable, first="drop", negatives="drop", nr=None, nan_policy=None):
    if not len(_iterable):
        return np.asarray(_iterable)
    np.seterr(invalid="ignore")
    def_policy = {"how": "previous", "fill_remaining": True, "if_all": "leave"}
    nan_policy = _nan_policy_vars(nan_policy, def_policy)
    # print(nan_policy)

    a = implement_nan_policy(_iterable, **nan_policy)
    # print(a)
    nan_list = ("nan", "np.nan", "numpy.nan", "math.nan")

    ucs = np.concatenate([a[:1], a[1:] - a[:-1]]).astype(float)
    """first_locs = np.arange(ucs.shape[0]) == 0
    neg_locs = ucs < 0"""
    if not ucs.shape[0]:
        return ucs

    for n, op in zip(("first", "negatives"), (first, negatives)):
        # ucs < 0 displays RuntimeWarning when encountering nan
        # locs = np.arange(ucs.shape[0]) == 0 if n=='first' else ucs < 0
        locs = [0] if n == "first" else np.where(ucs < 0)[0]

        if op == "leave":
            pass
        elif op == "drop":
            # ucs = ucs[~locs]
            ucs = np.delete(ucs, locs)
        elif isinstance(op, (int, float)):
            ucs[locs] = op
        elif isinstance(op, str) and op.lower() == "zero":
            ucs[locs] = 0
        elif (
            pd.isnull(op)
            or op is None
            or isinstance(op, str)
            and op.lower() in nan_list
        ):
            ucs[locs] = np.nan
        else:
            raise ValueError(n, op)

    if nr:
        ucs = ucs[-nr:]

    return ucs

    """else:
        #ucs = []
        for i,v in enumerate(_iterable[:0:-1]):
            dif = v - _iterable[-2-i]
            
            if excl_negatives and dif < 0: continue
            else: ucs.append(dif)
            
            if nr and len(ucs) >= nr:
                break
            
        ucs = ucs[::-1]"""


def _check_limits(limits):
    if len(limits) != 2:
        raise ValueError("Limits must contain 2 elements; got: {}".format(len(limits)))

    if limits[0] is not None and limits[0] > 0:
        raise ValueError("First limit must be <= 0; got: {}".format(limits[0]))

    if limits[1] is not None and limits[1] < 0:
        raise ValueError("Second limit must be >= 0; got: {}".format(limits[1]))

    if sum(x == 0 for x in limits) == 1 and None not in limits:
        raise ValueError(
            "Either both limits must be 0 or neither of them; got: {}".format(limits)
        )

    return True


def limiter(A, limits, closed="both"):
    if closed not in ("both", "left", "right", "neither", None):
        raise ValueError(
            "`closed` must be one of the following: (both,left,right,neither); got: {}".format(
                closed
            )
        )
    L0, L1 = limits

    if L0 is not None:
        op = (
            lambda x, y: x >= y
            if closed in ("both", "left", None)
            else lambda x, y: x > y
        )
        A = np.where(op(A, L0), A, np.nan)
    if L1 is not None:
        op = (
            lambda x, y: x <= y
            if closed in ("both", "right", None)
            else lambda x, y: x < y
        )
        A = np.where(op(A, L1), A, np.nan)

    if A.ndim > 1:
        return A[~np.isnan(A).any(axis=1)]
    else:
        return A[~np.isnan(A)]


def randomize_summation(
    _sum, n, limits=(-0.3, 0.3), closed="both", *, factor=15, sample_size=10
):
    limit_vs = (None, None)
    mean = 1 / n

    if limits is not None:
        _check_limits(limits)
        limit_vs = [mean * (1 + L) if L is not None else L for L in limits]

    if all(x == 0 for x in limit_vs):
        if closed not in ("both", None):
            raise ValueError(
                "`closed` must be 'both' if both limits are 0; got: {}".format(closed)
            )
        return np.ones(n) * mean

    while True:
        # A is a 2d array even if sample_size=1
        A = np.random.dirichlet(np.ones(n) * factor, size=sample_size)

        A2 = limiter(A, limit_vs, closed=closed)

        if not A2.shape[0]:
            factor *= 2
            # print(factor)
        else:
            break

    return A2[0] * _sum


def weight_limiter(A, weight_limits, closed="both"):
    if closed not in ("both", "left", "right", "neither", None):
        raise ValueError(
            "`closed` must be one of the following: (both,left,right,neither); got: {}".format(
                closed
            )
        )

    op1 = (
        (lambda x, y: x >= y)
        if closed in ("both", "left", None)
        else (lambda x, y: x > y)
    )
    op2 = (
        (lambda x, y: x <= y)
        if closed in ("both", "right", None)
        else (lambda x, y: x < y)
    )
    AT = A.transpose()
    at = []

    for i, limits in enumerate(weight_limits):
        L0, L1 = limits
        ATi = AT[i]
        if L0 is not None:
            ATi = np.where(op1(ATi, L0), ATi, np.nan)
        if L1 is not None:
            ATi = np.where(op2(ATi, L1), ATi, np.nan)
        at.append(ATi)

    AT = np.asarray(at, dtype=np.float64)
    A = AT.transpose()

    if A.ndim > 1:
        return A[~np.isnan(A).any(axis=1)]
    else:
        return A[~np.isnan(A)]


def randomize_weights(
    weights, limits=(-0.3, 0.3), closed="both", *, factor=15, sample_size=10
):
    weights = np.asarray(weights, dtype=np.float64)
    _sum = weights.sum()
    limit_vs = [(None, None)] * weights.size

    if limits is not None:
        _check_limits(limits)
        limit_vs = [
            [w * (1 + L) if L is not None else L for L in limits] for w in weights
        ]

    if all(x == 0 for x in limit_vs):
        if closed not in ("both", None):
            raise ValueError(
                "`closed` must be 'both' if both limits are 0; got: {}".format(closed)
            )
        return weights

    while True:
        # A is a 2d array even if sample_size=1
        A = np.random.dirichlet(weights * factor, size=sample_size) * _sum

        A2 = weight_limiter(A, limit_vs, closed=closed) if limits is not None else A

        if not A2.shape[0]:
            factor *= 2
            # print(factor)
        else:
            break

    return A2[0]


# ----------------------------------------------------------------------------
def verify_uniqueness(obj, index=True, columns=True, name=None):
    if isinstance(obj, pd.Series):
        columns = False

    if name is None:
        name_str = ""
    else:
        name_str = "{}'s "

    for attr, include in (("index", index), ("columns", columns)):
        if not include:
            continue

        ind = getattr(obj, attr)
        ind_duplicated = ind[ind.duplicated()]
        if not ind_duplicated.shape[0]:
            continue

        raise ValueError(
            "Duplicates in {}{}: {}".format(name_str, attr, ind_duplicated)
        )


def _get_valid(obj, valid_col=None, valid_func=None):
    # last_index = obj[valid_col].last_valid_index()
    is_series = isinstance(obj, pd.Series)

    if is_series:
        check_cols = [obj]
    elif valid_col:
        check_cols = [obj[valid_col]]
    else:
        check_cols = [x[1] for x in obj.iteritems()]

    last_index = -1
    obj_index = obj.index

    for s in check_cols:
        if valid_func:
            valid_indexes = s.apply(valid_func)
            if not valid_indexes.shape[0]:
                continue
            last_index = max(last_index, obj_index[valid_indexes][-1])
            continue

        valid_index = obj.last_valid_index()
        if valid_index is not None:
            continue
        last_index = max(last_index, valid_index)

    return last_index


def pd_replace(obj, obj2, start=None, valid_col=None, valid_func=None, simple=True):
    """If simple=True, then obj nor obj2 must contain non-unique indexes/columns.
    Otherwise if start has multiple matches in obj.index, last is chosen."""
    is_series = isinstance(obj, pd.Series)
    if simple:
        [
            verify_uniqueness(objx, columns=b_col, name=name)
            for objx, b_col, name in ((obj, True, "obj"), (obj2, False, "obj2"))
        ]

    if start is None:
        last_index = _get_valid(obj, valid_col, valid_func)

        if last_index != -1:
            entry_iloc = obj.index.get_loc(last_index) + 1
        else:
            entry_iloc = 0

    else:
        entry_iloc = obj.index.get_loc(start)

    if isinstance(entry_iloc, np.ndarray):
        # index was not unique, multiple matches
        entry_iloc = np.where(entry_iloc)[0][-1]

    end_iloc = entry_iloc + obj2.shape[0]
    missing = end_iloc - obj.shape[0]

    if missing > 0:
        I = IndexError("Obj short of {} rows".format(missing))
        I.missing = missing
        raise I

    # Note (example):
    # obj.index = [0,0] + list(obj.index[2:])
    # obj.iloc[0:2] = obj2
    # -> now both rows (0,0) are overwritten with the matching row of obj2
    # However, if obj2 has duplicates (0,0), it will not work

    if is_series:
        obj.iloc[entry_iloc:end_iloc] = obj2.values

    elif simple:
        ind0 = obj2.index
        obj2.index = obj.index[entry_iloc:end_iloc]

        overlapping_cols = np.where(obj.columns.isin(obj2.columns))[0]
        obj.iloc[entry_iloc:end_iloc, overlapping_cols] = obj2

        obj2.index = ind0

    else:
        obj_cols = obj.columns
        obj2_cols = obj2.columns
        obj2_cols_uniq_ind = np.where(~obj2_cols.duplicated())

        for col2_iloc in obj2_cols_uniq_ind:
            col2 = obj2_cols[col2_iloc]

            try:
                col_iloc = obj_cols.get_loc(col2)
            except KeyError:
                continue

            obj2_values = obj2.iloc[:, col2_iloc].values

            if isinstance(col_iloc, np.ndarray):
                col_iloc = np.where(col_iloc)[0]
                # list of matching columns (with identical name)
                obj2_values = [obj2_values for x in col_iloc]

            obj.iloc[entry_iloc:end_iloc, col_iloc] = obj2_values


if __name__ == "__main__":
    # print(randomize_summation(15.4,5))
    weights = [0.2, 0.8, 0.4, 0.6]
    rw = randomize_weights(weights, limits=(-0.05, 0.05))
    print(rw)

    tp = get_timestamps([np.timedelta64(td(minutes=60)), td(minutes=30)])
    print(tp)
    tp2 = get_timestamps(np.timedelta64(td(minutes=60)))
    print(tp2)
    tp3 = get_timestamps(dt(2016, 1, 1), "np.datetime64")
    print(tp3)
    tp4 = get_timestamps([td(days=60), dt(2016, 1, 1)], "pydatetime")
    print(tp4)
    print("\n Get_period_entries:")

    tp5 = (dt(2000, 1, 1), dt(2000, 1, 1, 5))
    pe = get_period_entries(tp5[0], tp5[1], freq=td(hours=1), exclude_end=False)
    for i, x in enumerate(pe[:-1]):
        x2 = pe[i + 1]
        print([x, x2])

        tp6 = get_timestamps((x, x2))
        print(tp6)

        tp7 = get_timestamps(tp6, "pd.TimeStamp")
        begin, end = tp7
        print((begin, end), "\n")

    tp8 = get_timestamps(["1D", None])
    print(tp8)

    tp9 = get_timestamps([dt(2000, 1, 1), None])
    print(tp9)

    so = slice_obj(pd.Series(np.arange(6), index=pe), (pe[2], td(hours=2)))
    print(so)
    so2 = slice_obj(list(pe), (pe[2], td(hours=2)))
    print(so2)
