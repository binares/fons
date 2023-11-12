import concurrent.futures
import asyncio
import functools
import platform

_IS_PY_10 = platform.python_version_tuple() >= ("3", "10", "0")


class FonsEvent(asyncio.Event):
    def __init__(self, *, loop=None):
        if _IS_PY_10:
            super().__init__()
            self._loop = loop or asyncio.get_event_loop()
        else:
            super().__init__(loop=loop)


class FonsQueue(asyncio.Queue):
    def __init__(self, maxsize=0, *, loop=None):
        if _IS_PY_10:
            super().__init__(maxsize)
            self._loop = loop or asyncio.get_event_loop()
        else:
            super().__init__(maxsize, loop=loop)


def _check_is_fons_queue(q):
    if not isinstance(q, FonsQueue):
        raise TypeError("Expected FonsQueue, got: {}".format(type(q)))


def _check_is_fons_event(e):
    if not isinstance(e, FonsEvent):
        raise TypeError("Expected FonsEvent, got: {}".format(type(e)))


def lrc(future_or_coro):
    return asyncio.get_event_loop().run_until_complete(future_or_coro)


def _set_cb_loop(future, cb_loop=None):
    # If cb_loop has not been set, make sure the current event loop
    # doesn't conflict with future's loop (if that loop is already running in
    # potentially another thread)
    if (
        cb_loop is None
        and isinstance(future, asyncio.Future)
        and future._loop.is_running()
    ):  # and asyncio.get_event_loop() is not future._loop:
        cb_loop = future._loop
    return cb_loop


def wrap_with_future(future, *, cb_loop=None, f=None):
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)
        if not is_async:

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # print('doing ({},{},{})'.format(asyncfunc.__name__,args,kwargs))
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    _cb_loop = _set_cb_loop(future, cb_loop)
                    if _cb_loop is None:
                        future.set_exception(e)
                    else:
                        _cb_loop.call_soon_threadsafe(
                            functools.partial(future.set_exception, e)
                        )
                else:
                    _cb_loop = _set_cb_loop(future, cb_loop)
                    if _cb_loop is None:
                        future.set_result(result)
                    else:
                        _cb_loop.call_soon_threadsafe(
                            functools.partial(future.set_result, result)
                        )
                return future

        else:

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # print('doing ({},{},{})'.format(asyncfunc.__name__,args,kwargs))
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    _cb_loop = _set_cb_loop(future, cb_loop)
                    if _cb_loop is None:
                        future.set_exception(e)
                    else:
                        _cb_loop.call_soon_threadsafe(
                            functools.partial(future.set_exception, e)
                        )
                else:
                    _cb_loop = _set_cb_loop(future, cb_loop)
                    if _cb_loop is None:
                        future.set_result(result)
                    else:
                        _cb_loop.call_soon_threadsafe(
                            functools.partial(future.set_result, result)
                        )
                return future

        return wrapper

    return decorator if f is None else decorator(f)


def call_via_loop(
    func,
    args=None,
    kwargs=None,
    *,
    future=None,
    module="concurrent.futures",
    loop=None,
    cb_loop=None
):
    """:param loop: by which the func will be executed
    :param cb_loop: loop which sets the result to the future; if left to None,
                    `wrap_with_future` itself ensures thread safety of the SET operation
    """
    if module not in ("concurrent.futures", "asyncio"):
        raise ValueError(module)

    if args is None:
        args = tuple()
    if kwargs is None:
        kwargs = {}

    if future is not None:
        pass
    elif module == "asyncio":
        future = asyncio.Future(loop=cb_loop)
    else:
        future = concurrent.futures.Future()

    if loop is None:
        loop = asyncio.get_event_loop()

    is_async = asyncio.iscoroutinefunction(func)

    wrapped = wrap_with_future(future, cb_loop=cb_loop)(func)
    if not is_async:
        p = functools.partial(wrapped, *args, **kwargs)
    else:
        p = functools.partial(
            asyncio.ensure_future, wrapped(*args, **kwargs), loop=loop
        )
    loop.call_soon_threadsafe(p)

    return future


def call_via_loop_afut(
    func, args=None, kwargs=None, *, future=None, loop=None, cb_loop=None
):
    return call_via_loop(
        func, args, kwargs, future=future, module="asyncio", loop=loop, cb_loop=cb_loop
    )
