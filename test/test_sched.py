import pytest
import warnings
from queue import Queue
import asyncio
import datetime

dt = datetime.datetime
td = datetime.timedelta
import time
import logging

from fons.log import quick_logging

logging.basicConfig(level=10)
# quick_logging(3, True)

from fons.sched import (
    Ticker,
    AsyncTicker,
    TickManager,
    AsyncTickManager,
    Routine,
    WaitException,
    QuitException,
    TerminatedException,
    AllTerminated,
)
import fons.time as fontime


# tfunc = lambda x: 2


def to_us(adt):
    us = adt.microsecond
    if us <= 0:
        return us

    while us < 100000:
        us *= 10

    return us


# ........................
gl_counter = 0
nr = 15


def tfunc(a, b, *, n=4):
    global gl_counter
    gl_counter += 1

    # time.sleep(0.0001)
    if not (gl_counter % nr):
        print("gl counter: {}, raising QuitException".format(gl_counter))
        raise QuitException

    return a + b + n


args = (1, 2)
kw = {"n": 4}


factor = 1
I = 0.01 * factor
D = 0.01


iu_counter = 1


def IU():
    global iu_counter
    new_i = I + 0.003 * factor * (iu_counter % 20)
    iu_counter += 1

    return new_i


def test_ticker():
    t = Ticker(tfunc, interval=I, sync=None, args=args, kw=kw, lock=0.2, keep=nr)
    IU2 = Ticker(IU, interval=I)
    t3 = Ticker(tfunc, interval=IU, sync=None, lock="next", args=args, kw=kw, keep=nr)

    t4 = Ticker(
        tfunc,
        interval=I,
        sync=td(0, 1),
        delay=D,
        lock="next",
        args=args,
        kw=kw,
        keep=nr,
    )
    t5 = Ticker(tfunc, interval=I, sync="first", delay=D, args=args, kw=kw, keep=nr)
    t6 = Ticker(
        tfunc,
        interval=IU,
        sync="first",
        delay=D,
        args=args,
        kw=kw,
        keep=nr,
        name="TickerX6",
    )

    for x in (t, t3, t4, t5, t6):
        for i in range(nr):
            try:
                x.tick()
            except WaitException as e:
                logging.info("{}, {}, sleeping {}".format(x._name, i, e.wait_time))
                # warnings.warn('{},{}, sleeping {}'.format(x._name,i,e.wait_time))
                time.sleep(e.wait_time)
                x.tick()
            finally:
                if i == nr - 1 and x in (t3, t4, t5, t6):
                    entries = list(x.entries)[::-1]
                    records = list(x.records)[::-1]
                    secs = [
                        "{}.{}".format(y.second, int(to_us(y) / 1000)) for y in entries
                    ]
                    difs = [
                        round((y - entries[i]) / td(seconds=1), int(4 / factor))
                        for i, y in enumerate(entries[1:])
                    ]
                    # difs2 = [round((y[1]-y[0])/td(seconds=1),6) for y in records]
                    logging.debug("{}\ndifs: {}\n".format(x._name, difs))  # ,difs2))

    for x in (t, t3, t4, t5, t6):
        assert x._closed
        with pytest.raises(TerminatedException):
            x.tick()


def test_ticker_thread():
    q = Queue()
    callback = lambda x: q.put(x["result"])
    t = Ticker(lambda: 2, interval=0, callback=callback, name="ThreadTicker")
    t.start_thread()

    a = q.get(timeout=0.2)
    assert a == 2

    t.close()
    assert t._closed
    with pytest.raises(TerminatedException):
        t.tick()


def test_synced():
    at = Ticker(interval="1T", sync="1T")
    synced = at._synced(dt(2018, 8, 4, 2, 5, 15, 1))
    assert synced == dt(2018, 8, 4, 2, 5)

    at.tick()
    assert at.entries[0] == fontime.dt_round(dt.utcnow(), "1T")
    assert int(at.get_time_remaining()) == 60 - dt.utcnow().second - 1


# ------------------------------------------


async def async_ticker():
    global gl_counter, iu_counter
    gl_counter = 0
    iu_counter = 1

    global nr
    nr = 3

    t = AsyncTicker(tfunc, interval=I, sync=None, args=args, kw=kw, lock=0.2, keep=nr)
    IU2 = AsyncTicker(IU, interval=I)
    t3 = AsyncTicker(
        tfunc, interval=IU, sync=None, lock="next", args=args, kw=kw, keep=nr
    )

    t4 = AsyncTicker(
        tfunc,
        interval=I,
        sync=td(0, 1),
        delay=D,
        lock="next",
        args=args,
        kw=kw,
        keep=nr,
    )
    t5 = AsyncTicker(
        tfunc, interval=I, sync="first", delay=D, args=args, kw=kw, keep=nr
    )
    t6 = AsyncTicker(
        tfunc,
        interval=IU,
        sync="first",
        delay=D,
        args=args,
        kw=kw,
        keep=nr,
        name="TickerX6",
    )

    for x in (t, t3, t4, t5, t6):
        for i in range(nr):
            try:
                await x.tick()
            except WaitException as e:
                logging.info("{}, {}, sleeping {}".format(x._name, i, e.wait_time))
                # warnings.warn('{},{}, sleeping {}'.format(x._name,i,e.wait_time))
                await asyncio.sleep(e.wait_time)
                await x.tick()
            finally:
                if i == nr - 1 and x in (t3, t4, t5, t6):
                    entries = list(x.entries)[::-1]
                    records = list(x.records)[::-1]
                    secs = [
                        "{}.{}".format(y.second, int(to_us(y) / 1000)) for y in entries
                    ]
                    difs = [
                        round((y - entries[i]) / td(seconds=1), int(4 / factor))
                        for i, y in enumerate(entries[1:])
                    ]
                    # difs2 = [round((y[1]-y[0])/td(seconds=1),6) for y in records]
                    logging.debug("{}\ndifs: {}\n".format(x._name, difs))  # ,difs2))

    for x in (t, t3, t4, t5, t6):
        with pytest.raises(TerminatedException):
            print("verifying error")
            await x.tick()
            print("THIS SHOULD NOT BE PRINTED")

    print("Async all passed")


loop = asyncio.get_event_loop()


def test_async_ticker():
    loop.run_until_complete(asyncio.gather(*[async_ticker()], return_exceptions=False))


# ------------------------------------------
def test_tick_manager():
    global gl_counter, iu_counter
    gl_counter = 0
    iu_counter = 1

    t = Ticker(tfunc, interval=I, sync=None, args=args, kw=kw, lock=0.2, keep=nr)
    t2 = Ticker(tfunc, interval=I, sync=None, args=args, kw=kw, lock=0.2, keep=nr)

    tm = TickManager([t, t2])
    tm.tick(errors="sleep")
    tm.tick(errors="sleep")

    t.close()
    tm.tick(errors="sleep")

    t2.close()

    with pytest.raises(AllTerminated):
        tm.tick()


# ------------------------------------------


async def async_tick_manager():
    global gl_counter, iu_counter
    gl_counter = 0
    iu_counter = 1

    cb = lambda x: print("{} completed at {}".format(x["ticker"]._name, dt.utcnow()))
    e1 = asyncio.Event()
    e2 = asyncio.Event()

    def cb2(e):
        def cb2_wapped(x):
            print("{} completed at {}".format(x["ticker"]._name, dt.utcnow()))
            e.set()

        return cb2_wapped

    t1 = AsyncTicker(
        tfunc,
        interval=I,
        sync=None,
        args=args,
        kw=kw,
        lock=0.2,
        keep=nr,
        callback=cb2(e1),
    )
    t2 = AsyncTicker(
        tfunc,
        interval=I,
        sync=None,
        args=args,
        kw=kw,
        lock=0.2,
        keep=nr,
        callback=cb2(e2),
    )
    tm = AsyncTickManager([t1, t2], loop=loop, allterminated="raise", callback=cb)

    await tm.tick()
    await tm.tick()

    print("waiting till e1 set")
    await e1.wait()
    print("wait complete")

    await t1.close()
    print("t1 closed x1")
    e2.clear()

    await tm.tick()

    print("waiting till e2 set")
    await e2.wait()
    print("wait complete")

    await t2.close()
    print("t2 closed")

    with pytest.raises(AllTerminated):
        await tm.tick()
    print("tm .tick() raised Allterminated")

    await tm.close()
    print("tm._closed: {}".format(tm._closed))
    with pytest.raises(TerminatedException):
        await tm.tick()
    print("tm .tick() raised TerminatedException")


def test_async_tick_manager():
    loop.run_until_complete(
        asyncio.gather(*[async_tick_manager()], return_exceptions=False)
    )


async def async_tick_manager_loop():
    global gl_counter, iu_counter
    gl_counter = 0
    iu_counter = 1

    cb = lambda x: print("{} ticked at {}".format(x["ticker"]._name, dt.utcnow()))
    e1 = asyncio.Event()
    e2 = asyncio.Event()
    e3 = asyncio.Event()

    def cb2(e):
        def cb2_wapped(x):
            print("{} ticked at {}".format(x["ticker"]._name, dt.utcnow()))
            e.set()

        return cb2_wapped

    t1 = AsyncTicker(
        tfunc,
        interval=I,
        sync=None,
        args=args,
        kw=kw,
        lock=0.2,
        keep=nr,
        callback=cb2(e1),
        name="AT-1 of AsyncTickManagerMAIN",
    )
    t2 = AsyncTicker(
        tfunc,
        interval=I,
        sync=None,
        args=args,
        kw=kw,
        lock=0.2,
        keep=nr,
        callback=cb2(e2),
        name="AT-2 of AsyncTickManagerMAIN",
    )
    tm = AsyncTickManager(
        [t1, t2],
        loop=loop,
        allterminated="raise",
        callback=cb,
        name="AsyncTickManagerMAIN",
    )

    # assert e1.is_set()
    # assert e2.is_set()

    # tickers are automatically terminated at loop #nr
    with pytest.raises(AllTerminated):
        await tm.loop()


def test_async_tick_manager_loop():
    loop.run_until_complete(
        asyncio.gather(*[async_tick_manager_loop()], return_exceptions=False)
    )


def test_routine():
    async def rout_func(d={"i": 0}, break_at=2):
        print(d)
        d["i"] += 1
        if d["i"] == break_at:
            print("breaking")
            raise QuitException

    sched = {
        "r1": {"target": rout_func, "kwargs": {"d": {"i": 0}}, "interval": 0.01},
        "r2": {"target": rout_func, "kwargs": {"d": {"i": 0}, "break_at": 4}},
    }
    rout = Routine(sched, tickmgr={"allterminated": "close"})
    loop.run_until_complete(asyncio.gather(*[rout.start()], return_exceptions=False))
    assert sched["r1"]["kwargs"]["d"]["i"] == 2
    assert sched["r2"]["kwargs"]["d"]["i"] == 4
    assert rout.get_event("r1").is_set()
    assert rout.get_event("r2").is_set()


# def test_asynctickmgr_with_nonasynctickers():


"""
r2 = 'new_return'

intervals = [td(seconds=0.1),0.1]
exp_intervals = [intervals[0]] *2

as_delay = [True,False,None,'e']

delay = [td(seconds=0.05),0.05,None,dt(2000,1,1)]
exp_delay = [delay[0]]*2 + [None,None]


@pytest.mark.parametrized("interval","as_delay","delay","sync","exp")
def test_basics(interval,as_delay,delay,sync,exp):
    t = Ticker(tfunc,interval,as_delay,delay,sync=sync)
    
    assert t._ui['delay'] == exp['delay']
    assert t._ui['as_delay'] == exp['as_delay']
    
    now = dt.utcnow()
    t.tick()
    
    assert t._ui["interval"] == fontime.freq_to_offset(exp["interval"])
    assert t.interval.delta = exp["interval"]
    assert t.get_last() > now
    assert t.get_actual_last() > now
    assert t.sync == exp["sync"]
    
    
def test_"""
