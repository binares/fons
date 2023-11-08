import pytest
import time
import fons.func as ffunc
from fons.func import limitcalls, limitcalls_f, limitcalls_m
from fons.errors import TerminatedException, WaitException


ffunc._LIMITCALLS_WARN_WHEN_SLEEP = True
ffunc._LIMITCALLS_STORE_GLOBALLY = True
LH = ffunc._LIMITCALLS_HISTORY

r = 4
m, p = (3, 1)
s = 0.5

# ------------------


@limitcalls_f(m)
def f_totalcalls():
    return r


@limitcalls_f(m, p)
def f_periodcalls(self):
    return r


def _test_totalcalls(func, *args, **kw):
    for i in range(m):
        assert func(*args, **kw) == r

    with pytest.raises(TerminatedException):
        func(*args, **kw)


def _test_periodcalls(func, *args, **kw):
    for i in range(m):
        assert func(*args, **kw) == r

    with pytest.raises(WaitException):  # as e_info:
        func(*args, **kw)

    time.sleep(p - s)
    with pytest.raises(WaitException):  # as e_info:
        func(*args, **kw)

    time.sleep(s)
    assert func(*args, **kw) == r


# ----------------------


def test_f_totalcalls():
    _test_totalcalls(f_totalcalls)


def test_f_periodcalls():
    _test_periodcalls(f_periodcalls, None)


# -------------------------
totalcalls_code = "def totalcalls%i(self,b,*args): return r"


def totalcalls0(self, b, *args):
    return r


for i in range(2, 5):
    # exec(totalcalls_code %i)
    exec("totalcalls%i = totalcalls0" % i)


# plain:
class A:
    @limitcalls_m(m)
    def totalcalls(self, b, *args):
        return r

    totalcalls2 = limitcalls_m(m)(totalcalls0)
    totalcalls3 = limitcalls_m(m, f=totalcalls0)

    @classmethod
    @limitcalls_f(m)
    def cls_totalcalls(cls, b, *args):
        return r

    @staticmethod
    @limitcalls_f(m)
    def static_totalcalls(b=None, *args):
        return r


class B(A):
    pass


a = A()
a2 = A()
b = B()


# induced:
class C:
    @limitcalls(m)
    def totalcalls(self, b, *args):
        return r

    totalcalls2 = limitcalls(m)(totalcalls0)
    totalcalls3 = limitcalls(m, f=totalcalls0)

    @classmethod
    @limitcalls(m)
    def cls_totalcalls(cls, b, *args):
        return r

    @staticmethod
    @limitcalls(m)
    def static_totalcalls(b=None, *args):
        return r

    # -----------
    # ON PURPOSE:

    @classmethod
    @limitcalls(m)
    def cls_totalcalls_self(self, b, *args):
        return r

    @staticmethod
    @limitcalls(m)
    def static_totalcalls_self(self, b, *args):
        return r


class D(C):
    pass


c, c2, d = C(), C(), D()


def _test_m_totalcalls(objs, funcname):
    for obj in objs:
        func = getattr(obj, funcname)

        _test_totalcalls(func, 1, None)


plain_m = [a, a2, b]
induced_m = [c, c2, d]
totalcalls_m_funcs = ["totalcalls", "totalcalls2", "totalcalls3"]


def test_m_totalcalls():
    for funcname in totalcalls_m_funcs:
        _test_m_totalcalls(plain_m, funcname)


def test_m_totalcalls_induced():
    for funcname in totalcalls_m_funcs:
        _test_m_totalcalls(induced_m, funcname)


# ------


def _test_cs_totalcalls(objs, funcname):
    _test_totalcalls(getattr(objs[0], funcname), {}, None)

    for cls in objs[1:]:
        with pytest.raises(TerminatedException):
            getattr(cls, funcname)({}, None)


plain = a, A, B, b, a2
induced = c, C, D, d, c2


def test_c_totalcalls():
    _test_cs_totalcalls(plain, "cls_totalcalls")


def test_c_totalcalls_induced():
    _test_cs_totalcalls(induced, "cls_totalcalls")


def test_s_totalcalls():
    _test_cs_totalcalls(plain, "static_totalcalls")


def test_s_totalcalls_induced():
    _test_cs_totalcalls(induced, "static_totalcalls")


def test_cls_totalcalls_induced_with_self():
    _test_cs_totalcalls(induced, "cls_totalcalls_self")


def test_s_totalcalls_induced_with_self():
    with pytest.raises(TypeError):
        # first param 'self' is dict, not hashable
        _test_cs_totalcalls(induced, "static_totalcalls_self")


@limitcalls(m)
def totalcalls_self(self, b, *args):
    return r


def test_f_totalcalls_induced_with_self():
    _test_totalcalls(totalcalls_self, {}, 2)


# ---------------------------------------

l_warn = limitcalls_f(m, action="warn")
l_log = limitcalls_f(m, action="log", logging_level=50)
l_sleep = limitcalls_f(m, p, action="sleep", logging_level=50)
l_null = limitcalls_f(m, action=None)


def test_actions():
    items = [l_warn, l_log, l_sleep, l_null]
    for dec in items:
        f = dec(lambda x: r)

        for i in range(m + 1):
            f(None)

    with pytest.raises(ValueError):
        limitcalls_f(m, action="sleep", logging_level=50)


"""nan = '_nan_'
from collections import OrderedDict as OD

params = [['p',2],
          ['q', 4],
          ['t','T'],
          ['*',nan],
          ['*args', nan],
          ['**kw', nan]]

darams = OD(params)

params = [[],
          ['p'],
          ['p','q=4'],
          ['p=2, *args'],
          ['p=2, *, q=4, **kw'],
          ['self'],
          ['self=a'],
          ['self=None'],
          ['*self, p=2'],
          ['**self']]

decorators = ['@limicalls_f(m,p)','@limitcalls_m(m,p)','@limitcalls(m,p)']"""
