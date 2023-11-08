import pytest
import asyncio

from fons.aio import call_via_loop


async def asyncfunc(arg, *, kw=1):
    return arg / kw


async def _afunc():
    await asyncio.sleep(0.01)


def test_call_via_loop():
    loop = asyncio.get_event_loop()
    f = call_via_loop(asyncfunc, (4,), {"kw": 2})
    loop.run_until_complete(_afunc())
    assert f.result(0.1) == 2

    f = call_via_loop(asyncfunc, (4,), {"kw": 0})
    loop.run_until_complete(_afunc())
    with pytest.raises(ZeroDivisionError):
        assert f.result(0.1)


if __name__ == "__main__":
    test_call_via_loop()
