import datetime

dt = datetime.datetime
td = datetime.timedelta

from fons.threads import EliThread


def raise_RuntimeError(counter=None):
    if counter:
        counter["i"] += 1
    raise RuntimeError


def test_EliThread_keepalive():
    counter = {"i": 0}
    t = EliThread(
        target=raise_RuntimeError,
        args=(counter,),
        keepalive={"pause": 0.01, "attempts": 4},
        name="RuntimeRaisingEliThread",
    )
    started = dt.utcnow()
    t.start()
    t.join(0.08)
    assert counter["i"] == 4
    assert dt.utcnow() - started > td(seconds=0.04)
    assert not t.is_alive()
