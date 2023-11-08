import pandas as pd
import numpy as np
import math

from fons.pyops import compare


class Implemented:
    def __init__(self, na_values=[]):
        self.na_values = tuple(na_values)

    def __call__(self, *args):
        return self.all(*args)

    def any(self, *args):
        if not len(args):
            return False

        if all(
            isinstance(x, Implemented)
            or any(compare(x, na) for na in self.na_values)
            or type(x) is type
            and issubclass(x, Implemented)
            for x in args
        ):
            return False

        return True

    def all(self, *args):
        if not len(args):
            return False

        if any(
            isinstance(x, Implemented)
            or any(compare(x, na) for na in self.na_values)
            or type(x) is type
            and issubclass(x, Implemented)
            for x in args
        ):
            return False

        return True

    def __bool__(self):
        return False

    def __str__(self):
        return "nan"


# Any instance of Implemented is not implemented
# Impd(Impd) -> False
# Nor is Implemented class itself implemented
# Impd(Implemented) -> False

Impd = impd = nan = Implemented()
nImpd = Implemented([None])
pdImpd = Implemented([None, math.nan, np.nan, pd.NaT])


def is_implemented(*objects, **kw):
    if "na_values" in kw:
        _impd = Implemented(kw["na_values"])
    else:
        _impd = Impd
    return _impd(*objects)


if __name__ == "__main__":
    print(Impd(Implemented))
    print(Impd(nan))
    print(Impd(None))
    print(Impd(None, Implemented))
    print(Impd(None, nan))
