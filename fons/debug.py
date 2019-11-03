import sys, pdb, traceback
import warnings
import datetime
dt = datetime.datetime
td = datetime.timedelta
import asyncio
import threading

import fons.log as _log
logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)


def debug():
    type, value, tb = sys.exc_info()
    traceback.print_exc()
    pdb.post_mortem(tb)


def info(type, value, tb):
    if hasattr(sys, 'ps1') or not sys.stderr.isatty():
        # we are in interactive mode or we don't have a tty-like
        # device, so we call the default hook
        sys.__excepthook__(type, value, tb)
    else:
        import traceback, pdb
        # we are NOT in interactive mode, print the exception...
        traceback.print_exception(type, value, tb)
        print
        # ...then start the debugger in post-mortem mode.
        pdb.post_mortem(tb)


def set_pm_hook():
    #Only set the excepthook if it hasn't already been set
    # (pydev debugger sets its own, and substituting it with our
    #  hook will cause the debugger post mortem interactive mode to fail)
    if sys.excepthook is sys.__excepthook__:
        sys.excepthook = info
    elif sys.excepthook is not info:
        warnings.warn('Ignoring excepthook set request because it has already been set by another debugger.')


def trylog(f, args=None, kwargs=None, attempts=1, return2=NotImplemented,*,
           catch=Exception, throw=None, raise_throw=True, display=True, pause=0, exit_on=None):
    if args is None: args = tuple()
    if kwargs is None: kwargs = {}
    i, exc = 0, None
    attempts_exceeded = lambda: attempts is not True and i >= attempts
    if throw is None: throw = tuple()
    elif isinstance(throw, type):
        throw = (throw,)
    elif not isinstance(throw, tuple):
        throw = tuple(throw)
    if exit_on is None:
        exit_on = threading.Event()
    
    while not attempts_exceeded():
        i += 1
        try: return f(*args, **kwargs)
        except catch as e:
            exc = e
            if display:
                logger2.error(e)
            logger.exception(e)
            throw_e = isinstance(e, throw)
            if throw_e and raise_throw:
                raise e
            elif throw_e:
                break
        if exit_on.wait(pause):
            break
    
    if return2 is NotImplemented and exc is not None:
        raise exc
    
    return return2


async def asyncTryLog(f, args=None, kwargs=None, attempts=1, return2=NotImplemented,*,
                      catch=Exception, throw=None, raise_throw=True, display=True, pause=0, exit_on=None):
    if args is None: args = tuple()
    if kwargs is None: kwargs = {}
    i, exc = 0, None
    attempts_exceeded = lambda: attempts is not True and i >= attempts
    if throw is None: throw = tuple()
    elif isinstance(throw, type):
        throw = (throw,)
    elif not isinstance(throw, tuple):
        throw = tuple(throw)
    if exit_on is None:
        exit_on = asyncio.Event()
    
    while not attempts_exceeded():
        i += 1
        try: return await f(*args, **kwargs)
        except catch as e:
            exc = e
            if display:
                logger2.error(e)
            logger.exception(e)
            throw_e = isinstance(e, throw)
            if throw_e and raise_throw:
                raise e
            elif throw_e:
                break
        try: await asyncio.wait_for(exit_on.wait(), pause)
        except asyncio.TimeoutError: pass
        else: break
    
    if return2 is NotImplemented and exc is not None:
        raise exc
    
    return return2

aTryLog = asyncTryLog


def safeTry(f, args=None, kwargs=None, attempts=1, return2=None, *,
            catch=Exception, throw=[], raise_throw=True, display=True, pause=0, exit_on=None):
    return trylog(f, args, kwargs, attempts, return2, catch=catch, throw=throw,
                  raise_throw=raise_throw, display=display, pause=pause, exit_on=exit_on)


async def safeAsyncTry(f, args=None, kwargs=None, attempts=1, return2=None, *,
                       catch=Exception, throw=[], raise_throw=True, display=True, pause=0, exit_on=None):
    return await asyncTryLog(f, args, kwargs, attempts, return2, catch=catch, throw=throw,
                             raise_throw=raise_throw, display=display, pause=pause, exit_on=exit_on)

safeATry = safeAsyncTry


def wrap_trylog(f, attempts=1, return2=NotImplemented, *,
                catch=Exception, throw=[], raise_throw=True, display=True, pause=0, exit_on=None):
    iscoro = asyncio.iscoroutinefunction(f)
    if not iscoro:
        def trylog_wrapper(*args, **kw):
            return trylog(f, args, kw, attempts, return2, catch=catch, throw=throw,
                          raise_throw=raise_throw, display=display, pause=pause, exit_on=exit_on)
    else:
        async def trylog_wrapper(*args, **kw):
            await asyncTryLog(f, args, kw, attempts, return2, catch=catch, throw=throw,
                              raise_throw=raise_throw, display=display, pause=pause, exit_on=exit_on)
    return trylog_wrapper

#------
async def safewait(coro, timeout):
    try: await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError: pass

#-------------------------------------------------


if __name__ == '__main__':
    #import pydevd
    #pydevd.GetGlobalDebugger().setExceptHook(Exception, True, False)
    #If run in eclipse pydev will cause to terminate the code after exception occurs
    set_pm_hook()
    def f():
        i = 0
        print(3/i)
    def main():
        f()
    main()
