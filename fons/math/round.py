import math
import numpy as np
from builtins import round as _round


def round_sd(x, sigdigits=3, method="round", accuracy=None):
    if np.isnan(x):
        return np.nan
    elif x == 0:
        return 0

    dist = math.floor(math.log10(abs(x)))
    n = -dist + sigdigits - 1
    return round(x, n, method, accuracy)

    # q = math.pow(10,-dist+keep-1)
    # return math.trunc(x*q) / q


def ignore_half_round(n):
    if abs(n - int(n)) < 0.5:
        return math.floor(n) if n > 0 else math.ceil(n)
    else:
        return math.ceil(n) if n > 0 else math.floor(n)


def round(x, ndigits, method="round", accuracy=None):
    """`accuracy` only applies to non-"round" methods.
    Use it to weed out non-precise values:
     round(2.0000000000000001, 0, 'ceil', 8) -> 2.0"""
    method = method.lower()
    if accuracy is None:
        pass
    elif not isinstance(accuracy, int):
        raise TypeError(type(accuracy))
    elif accuracy < 0:
        raise ValueError(accuracy)

    rrounded = _round(x, ndigits)

    if method == "round":
        return rrounded

    if method in ("down", "floor", "truncate", "int"):
        f = int
        f2 = math.ceil
    elif method in ("up", "ceil"):
        f = math.ceil
        f2 = int
    else:
        raise ValueError(method)

    # x has no non-zero digits after n (this eliminates errors
    # that could otherwise arise due to multiplication)
    if rrounded == x:
        return x

    factor = pow(10, ndigits)
    p = x * factor

    # Examples:
    # round(8.2991, 1, 'floor', 2) -> 8.3
    # round(8.3001, 1, 'ceil', 2) -> 8.3
    if accuracy is not None and accuracy != 0:
        factor2 = pow(10, accuracy)
        p = f2(p * factor2) / factor2

    return f(p) / factor
