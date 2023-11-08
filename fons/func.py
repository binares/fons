from functools import wraps
from inspect import currentframe, getargvalues, getfullargspec

import traceback
import platform
import copy
import time
import datetime

dt = datetime.datetime
td = datetime.timedelta

from collections import deque
from queue import Queue
import asyncio
import math
import warnings
import logging
import inspect

from fons.errors import WaitException, TerminatedException


_LIMITCALLS_STORE_GLOBALLY = False
_LIMITCALLS_PARAMS = {}
_LIMITCALLS_HISTORY = {}

_LIMITCALLS_LOGGING_LEVEL = logging.WARNING
_LIMITCALLS_SLEEP_LOGGING_LEVEL = logging.DEBUG
_LIMITCALLS_WARN_WHEN_SLEEP = False
_LIMITCALLS_RETAIN_ORDER = False

_PLATFORM = platform.system()


# If method called as static, initializes necessary attributes (passed as kwargs)
#   to class (instead of instance), without changing the original class attrbs
# If called as class but without kwargs, assumes class already has those attrbs


class hybridmethod(object):
    def __init__(self, func):
        self.func = func

    def __get__(self, obj, cls):
        context = obj if obj is not None else cls

        # create new class to not overwrite its attrbs
        if context is cls:

            class NewoO(context):
                pass

            context = NewoO
            K_name = cls.__name__
            K_name_part = "__" + K_name + "_"

            for attr_name in vars(cls):
                if K_name_part in attr_name and attr_name[-2:] != "__":
                    attr_short = attr_name.replace(K_name_part, "")
                    attr_value = getattr(cls, attr_name)
                    setattr(context, "__" + attr_short, copy.deepcopy(attr_value))

        @wraps(self.func)
        def hybrid(*args, **kw):
            # inits only if context is class (not self (instance))
            # offers to not init some kw for class too:
            init_kw = kw
            if "_static_vars" in kw:
                init_kw = {k: v for k, v in kw.items() if k not in kw["_static_vars"]}
                kw = {k: v for k, v in kw.items() if k in kw["_static_vars"]}
                del init_kw["_static_vars"]
            else:
                init_kw = kw.copy()
                # kw = {}

            for k, v in init_kw.items():
                try:
                    # checks if is class (don't want to overwrite self attrbs):
                    if isinstance(context, type):
                        setattr(context, k, v)
                except Exception:
                    traceback.print_exc()

            return self.func(context, *args, **kw)

            # Exceptions (when one *must* use _static_vars):
            # instance method checks if it has attr which's name also happens to be in its kwargs
            # (therefore answer would always be "yes" if we init it to class 'New')
            # if a kwarg happens to be an attr of *class* "context" aswell
            # (although I can differ an instance from class/static, I can't
            #  differ class from static (since static is called *from* the class)
            #  therefore if its a class its attr is overwritten with the kwarg)

        # optional, mimic methods some more
        hybrid.__func__ = hybrid.im_func = self.func
        hybrid.__self__ = hybrid.im_self = context

        return hybrid


def obj_to_class(obj):
    klass = obj
    if not isinstance(obj, type):
        klass = eval(obj.__class__.__name__)

    return klass


def mro_without_wrapper(obj):
    klass = obj_to_class(obj)

    loc = next(
        (
            i
            for i, k in enumerate(klass.mro())
            if "hybridmethod" not in k or "NewoO" not in k
        ),
        0,
    )

    mro_list = klass.mro()[loc:]

    return mro_list


# like super(klass), except for 'NewoO'-s is returned its grandparent
def superb(cls):
    mro_list = mro_without_wrapper(cls)
    superklass = eval(mro_list[1].__name__)
    return superklass


def superclasses(obj):
    klass = obj_to_class(obj)

    if klass is not obj:
        # method was called from instance
        loc = 1
    else:
        # method was called from class
        loc = next(
            (
                i
                for i, k in enumerate(klass.mro())
                if "hybridmethod" not in k or "NewoO" not in k
            ),
            None,
        )

        if loc is None:
            return

    superklasses = [eval(k.__name__) for k in klass.mro()[loc:-1]]
    # all classes above the class of obj, except the last one ('object')
    # will they evaluate if in different modules? probably yes

    return superklasses


def find_all_double_underscore_vars(obj, var_name, superklasses=None):
    if not isinstance(superklasses, (tuple, list)):
        superklasses = superclasses(obj)

    sk = superklasses[:]
    sk.insert(0, obj_to_class(obj))

    a_list = []

    for K in sk:
        try:
            a_list.append(eval("K._{}__{}".format(K.__name__, var_name)))
        except Exception:
            pass

    return a_list


def get_arg_count(f):
    argspec = inspect.getfullargspec(f)
    if argspec.varargs:
        return math.inf
    # from_i = 0 if not argspec.args or argspec.args[0] != 'self' else 1
    # inspect.ismethod is accurate whether or not "self" is first arg,
    # or when it only has *args; works for classmethods (initated or not) too
    from_i = 0 if not inspect.ismethod(f) else 1
    return len(argspec.args[from_i:])


# ----------------------------------------------------------------------------


def _has_self(f):
    fas = getfullargspec(f)
    args = fas[0]

    if len(args) and args[0] == "self":
        return True

    return False


def _resolve_instance(func, args, bound, bound2):
    if hasattr(bound, "__call__"):
        instance = bound(args[0])

    elif bound:
        instance = args[0]

    elif bound2 and not isinstance(args[0], type):
        # user has left bound=None, and first param is "self"
        # only accept if args[0] is not cls (accidental classmethod)
        # (we don't want to *accidentally* use cls as the identifier,
        # because the cls would differ for subclasses while the function is same)
        instance = args[0]

    else:
        instance = None

    if not hasattr(instance, "__hash__"):
        first_param = getfullargspec(func)["args"][0]

        raise TypeError(
            (
                'Function "{}" is bound, '
                'but its first param "{}" of type {} is not hashable'
            ).format(func.__name__, first_param, type(instance))
        )

    return instance


def _get_msg(func, instance, text):
    if instance is not None:
        txt0 = "Limitcall on method {} of instance {}: ".format(func.__name__, instance)
    else:
        txt0 = "Limitcall on function {}: ".format(func.__name__)

    msg = txt0 + text.strip()

    return msg


"""class _TimeShort:
    def __init__(self, deq, interval):
        self.deq = deq
        self.interval = interval
        
    def __call__(self):
        nearest_next = self.deq[0] + self.interval
        self.time_short = time_short = (nearest_next - dt.utcnow())/td(seconds=1)
        
        return time_short
    
    __slots__ = ['deq','interval','time_short']"""


def _handle_action(
    action, msg, logging_level, exception=None, args=[], kwargs={}, sleep_time=0
):
    if action == "error":
        raise exception(*args, **kwargs)
    elif action == "warn":
        warnings.warn(msg)
    elif action == "log":
        logging.log(logging_level, msg)

    elif action == "sleep":
        msg += " --- sleeping {}s".format(round(sleep_time, 3))
        logging.log(logging_level, msg)

        if _LIMITCALLS_WARN_WHEN_SLEEP:
            warnings.warn(msg)

        time.sleep(sleep_time)


def _handle_request(func, PARAMS, QUEUES, HISTORY, instance=None):
    limit, interval, action, logging_lvl = PARAMS

    if instance is None:
        deq = HISTORY["func"]
        queue = QUEUES["func"]

    elif instance not in HISTORY["instances"]:
        HISTORY["instances"][instance] = deq = deque(maxlen=limit)
        QUEUES["instances"][instance] = queue = Queue(1)

    else:
        deq = HISTORY["instances"][instance]
        queue = QUEUES["instances"][instance]

    lvl = logging_lvl if queue.full() else 0
    logging.log(lvl, _get_msg(func, instance, "waiting on lock"))

    try:
        queue.put(None)
        logging.log(lvl, _get_msg(func, instance, "lock acquired"))

        if len(deq) < limit:
            deq.append(time.time())
            return
        elif interval is None:
            msg = _get_msg(
                func, instance, "has reached its total max calls {}".format(limit)
            )
            _handle_action(action, msg, logging_lvl, TerminatedException, [msg])
            return

        # If action is 'sleep', in every cycle the lock will be released before the sleep,
        # (so that the other calls don't have to wait), then acquired again
        # repeated until time_short > 0

        while True:
            nearest_next = deq[0] + interval
            wait_time = nearest_next - time.time()
            if wait_time <= 0:
                break

            msg = _get_msg(
                func, instance, "calls blocked for {}s.".format(round(wait_time, 3))
            )
            _handle_action(
                action,
                msg,
                logging_lvl,
                WaitException,
                [wait_time],
                {"msg": msg},
                wait_time,
            )

            if action != "sleep":
                break

        deq.append(time.time())

    finally:
        queue.get()


# Note: methods of instances of same class have different ids,
#      but limitcalls makes no difference, since it first wraps
#      during the time of class initiation
#      set 'bound' to True (or leave None) for each instance calls
#        to method be counted separately


def limitcalls(limit, interval=None, action="error", bound=None, **kw):
    """Decorator for counting the calls to the decorated function.
    Args:
     limit (int):
       number of maximum calls [absolute or periodic] to the function
       if exceeded, action is taken

     interval (int,float,timedelta,::None):
       ::None - limit is absolute (action taken if total > limit)
       ::<int,float> -> converted to timedelta(seconds(int,float))
       ::<timedelta> - calls are timestamped, action taken if rate is exceeded in interval (now-timedelta, now)

     action (str/None):
       what happens when call rate is exceeded
       ::error - raises TerminatedException if interval=None and limit exceeded,
                 raises WaitException if interval!= None and limit exceeded
       ::sleep - sleeps till nr_calls won't exceed limit in interval, then proceeds
       ::warn  - warns user with the error message, but proceeds
       ::log   - logs the error message, but proceeds
       ::None  - does nothing if call rate exceeded, proceeds with call

     bound (bool):
       if method, then whether the calls to are counted separately by each instance
       IMPORTANT: does not differentiate inherited methods from their source (i.e A.a == B(A).a [if a was inherited])
       ::True - first arg is assumed to be 'self', calls to func counted separately by each instance
       ::False - calls to func counted universally
       ::<callable> - instance is resolved by <callable>(args[0])
       ::None - auto-detects if the function is defined in class and has 'self' as first param,
                if so then bound = True, otherwise False
                Fails if: -method *without* "self" as first param (but intended to be bound)
                          -method was defined outside class (and intended to be bound)
                          -@staticmethod with "self" as first param
                          In those cases if you're lazy typing bound=True/False,
                           use @limitcalls_f / @limitcalls_m instead

    **kw:
     logging_level (int):
       logging level for error messages if action == 'log' / 'sleep'
       DEFAULT: DEBUG for 'sleep' action, WARNING for 'log'
     f (function):
       if used not as decorator (@limitcalls), but for converting an existing function,
       can do new_f = limitcalls(...,f=f) [instead of new_f = limitcalls(...)(f)]"""

    if isinstance(interval, td):
        interval = interval.total_seconds()

    elif interval is None and action == "sleep":
        raise ValueError('Action cannot be "sleep" if interval not specified.')

    elif not isinstance(interval, (int, float, type(None))):
        raise TypeError(type(interval))

    if not isinstance(limit, int):
        raise TypeError(type(limit))

    if action == "sleep":
        logging_lvl = _LIMITCALLS_SLEEP_LOGGING_LEVEL
    else:
        logging_lvl = _LIMITCALLS_LOGGING_LEVEL

    if kw.get("logging_level") is not None:
        logging_lvl = kw["logging_level"]

    if hasattr(bound, "__call__"):
        pass
    elif not isinstance(bound, (bool, type(None))):
        raise TypeError(type(bound))

    if not isinstance(action, (str, type(None))):
        raise TypeError(type(action))

    elif action not in ("error", "sleep", "warn", "log", None):
        raise ValueError(action)

    f = kw.get("f")

    def actual_decorator(func):
        PARAMS = (limit, interval, action, logging_lvl)
        QUEUES = {"func": Queue(1), "instances": {}}
        HISTORY = {"func": deque(maxlen=limit), "instances": {}}

        bound2 = bound
        # note to self:
        # cannot do: bound = new_value
        # (for some bound cannot be overwritten, otherwise it is lost from locals)

        # check if has self (eliminates ordinary funcs and @classmethod/@staticmethod,
        #                   assuming user has *not* defined self as first param)
        # if has "self" as first param, checks if the func is defined in the body of class
        #  (further eliminates functions defined outside class' [0th level] body )
        #  --note that __qualname__ may be given in other situations too
        #  --but tested that it *wasn't* present if the body was module or function

        # Note: the functionality still remains even if @classmethod has "self" as first param
        #  because first input param cls remains the same; however that is only implemented if
        #  bound = True; if left to None the inherited classmethods will be treated as identical

        if bound2 is not None:
            pass
        elif not _has_self(func):
            bound2 = False
        else:
            # __qualname__ only given if frame is located in the body of a class
            frame = currentframe().f_back
            if f:
                frame = frame.f_back

            # getargvalues returns namedtuple
            fr_locals = getargvalues(frame).locals
            # print(fr_locals.get('__qualname__'), '__qualname__' in fr_locals, func.__name__)

            try:
                bound2 = fr_locals["__qualname__"] is not None
            except KeyError:
                bound2 = False

        @wraps(func)
        def wrapper(*args, **kw):
            instance = _resolve_instance(func, args, bound, bound2)
            _handle_request(func, PARAMS, QUEUES, HISTORY, instance)

            return func(*args, **kw)

        if _LIMITCALLS_STORE_GLOBALLY:
            _LIMITCALLS_PARAMS[wrapper] = PARAMS
            _LIMITCALLS_HISTORY[wrapper] = HISTORY

        return wrapper

    if f:
        return actual_decorator(f)

    return actual_decorator


def limitcalls_f(limit, interval=None, action="error", **kw):
    """For ordinary functions and classmethods/staticmethods,
    or if calls to method are not intended do be counted separately for each instance"""
    return limitcalls(limit, interval, action, bound=False, **kw)


def limitcalls_m(limit, interval=None, action="error", **kw):
    """For methods"""
    return limitcalls(limit, interval, action, bound=True, **kw)


# -------------------------------------------------------------------------------------------


async def _async_handle_action(
    action,
    msg,
    logging_level,
    exception=None,
    args=[],
    kwargs={},
    sleep_time=0,
    lock=None,
    retain_order=False,
):
    if action == "error":
        raise exception(*args, **kwargs)
    elif action == "warn":
        warnings.warn(msg)
    elif action == "log":
        logging.log(logging_level, msg)

    elif action == "sleep":
        msg += " --- sleeping {}s".format(round(sleep_time, 2))
        logging.log(logging_level, msg)

        if _LIMITCALLS_WARN_WHEN_SLEEP:
            warnings.warn(msg)

        if lock is not None and lock.locked() and not retain_order:
            lock.release()

        await asyncio.sleep(sleep_time)

        if lock is not None and not retain_order:
            await lock.acquire()


async def _async_handle_request(func, PARAMS, LOCKS, HISTORY, instance=None):
    limit, interval, action, logging_lvl, retain_order = PARAMS

    if instance is None:
        deq = HISTORY["func"]
        lock = LOCKS["func"]

    elif instance not in HISTORY["instances"]:
        HISTORY["instances"][instance] = deq = deque(maxlen=limit)
        LOCKS["instances"][instance] = lock = asyncio.Lock()

    else:
        deq = HISTORY["instances"][instance]
        lock = LOCKS["instances"][instance]

    lvl = logging_lvl if lock.locked() and retain_order else 0
    logging.log(lvl, _get_msg(func, instance, "waiting on lock"))

    try:
        await lock.acquire()
        logging.log(lvl, _get_msg(func, instance, "lock acquired"))

        if len(deq) < limit:
            deq.append(time.time())
            return
        elif interval is None:
            msg = _get_msg(
                func, instance, "has reached its total max calls {}".format(limit)
            )
            await _async_handle_action(
                action,
                msg,
                logging_lvl,
                TerminatedException,
                [msg],
                retain_order=retain_order,
            )
            return

        # If action is 'sleep', in every cycle the lock will be released before the sleep,
        # (so that the other calls don't have to wait), then acquired again
        # repeated until time_short > 0
        lowest = 0.001 if _PLATFORM != "Windows" else 0.016

        while True:
            nearest_next = deq[0] + interval
            wait_time = nearest_next - time.time()
            if wait_time <= 0:
                break

            # Note that on asyncio asleeping nything below 1 ms won't work
            # and on Windows it may sleep as much as ~15 ms less
            # However the while loop will eliminate that problem.
            wait_time = max(lowest, wait_time)
            msg = _get_msg(
                func, instance, "calls blocked for {}s.".format(round(wait_time, 2))
            )
            await _async_handle_action(
                action,
                msg,
                logging_lvl,
                WaitException,
                [wait_time],
                {"msg": msg},
                wait_time,
                lock,
                retain_order=retain_order,
            )

            if action != "sleep":
                break

        deq.append(time.time())

    finally:
        lock.release()


def async_limitcalls(limit, interval=None, action="error", bound=None, **kw):
    """Decorator for counting the calls to the decorated function.
    Args:
     limit (int):
       number of maximum calls [absolute or periodic] to the function
       if exceeded, action is taken

     interval (int,float,timedelta,::None):
       ::None - limit is absolute (action taken if total > limit)
       ::<int,float> -> converted to timedelta(seconds(int,float))
       ::<timedelta> - calls are timestamped, action taken if rate is exceeded in interval (now-timedelta, now)

     action (str/None):
       what happens when call rate is exceeded
       ::error - raises TerminatedException if interval=None and limit exceeded,
                 raises WaitException if interval!= None and limit exceeded
       ::sleep - sleeps till nr_calls won't exceed limit in interval, then proceeds
       ::warn  - warns user with the error message, but proceeds
       ::log   - logs the error message, but proceeds
       ::None  - does nothing if call rate exceeded, proceeds with call

     bound (bool):
       if method, then whether the calls to are counted separately by each instance
       IMPORTANT: does not differentiate inherited methods from their source (i.e A.a == B(A).a [if a was inherited])
       ::True - first arg is assumed to be 'self', calls to func counted separately by each instance
       ::False - calls to func counted universally
       ::<callable> - instance is resolved by <callable>(args[0])
       ::None - auto-detects if the function is defined in class and has 'self' as first param,
                if so then bound = True, otherwise False
                Fails if: -method *without* "self" as first param (but intended to be bound)
                          -method was defined outside class (and intended to be bound)
                          -@staticmethod with "self" as first param
                          In those cases if you're lazy typing bound=True/False,
                           use @limitcalls_f / @limitcalls_m instead

    **kw:
     logging_level (int):
       logging level for error messages if action == 'log' / 'sleep'
       DEFAULT: DEBUG for 'sleep' action, WARNING for 'log'
    retain_order (bool):
       whether or not function call order is retained when blocked by lock
       DEFAULT: False
    loop:
      event loop for the Lock
     f (function):
       if used not as decorator (@limitcalls), but for converting an existing function,
       can do new_f = limitcalls(...,f=f) [instead of new_f = limitcalls(...)(f)]"""

    if isinstance(interval, td):
        interval = interval.total_seconds()

    elif interval is None and action == "sleep":
        raise ValueError('Action cannot be "sleep" if interval not specified.')

    elif not isinstance(interval, (int, float, type(None))):
        raise TypeError(type(interval))

    if not isinstance(limit, int):
        raise TypeError(type(limit))

    if action == "sleep":
        logging_lvl = _LIMITCALLS_SLEEP_LOGGING_LEVEL
    else:
        logging_lvl = _LIMITCALLS_LOGGING_LEVEL

    if kw.get("logging_level") is not None:
        logging_lvl = kw["logging_level"]

    if kw.get("retain_order") is not None:
        retain_order = kw["retain_order"]
    else:
        retain_order = _LIMITCALLS_RETAIN_ORDER

    if hasattr(bound, "__call__"):
        pass
    elif not isinstance(bound, (bool, type(None))):
        raise TypeError(type(bound))

    if not isinstance(action, (str, type(None))):
        raise TypeError(type(action))

    elif action not in ("error", "sleep", "warn", "log", None):
        raise ValueError(action)

    loop = kw.get("loop")
    f = kw.get("f")

    def actual_decorator(func):
        PARAMS = (limit, interval, action, logging_lvl, retain_order)
        LOCKS = {"func": asyncio.Lock(loop=loop), "instances": {}}
        HISTORY = {"func": deque(maxlen=limit), "instances": {}}

        bound2 = bound
        # note to self:
        # cannot do: bound = new_value
        # (for some bound cannot be overwritten, otherwise it is lost from locals)

        # check if has self (eliminates ordinary funcs and @classmethod/@staticmethod,
        #                   assuming user has *not* defined self as first param)
        # if has "self" as first param, checks if the func is defined in the body of class
        #  (further eliminates functions defined outside class' [0th level] body )
        #  --note that __qualname__ may be given in other situations too
        #  --but tested that it *wasn't* present if the body was module or function

        # Note: the functionality still remains even if @classmethod has "self" as first param
        #  because first input param cls remains the same; however that is only implemented if
        #  bound = True; if left to None the inherited classmethods will be treated as identical

        if bound2 is not None:
            pass
        elif not _has_self(func):
            bound2 = False
        else:
            # __qualname__ only given if frame is located in the body of a class
            frame = currentframe().f_back
            if f:
                frame = frame.f_back

            # getargvalues returns namedtuple
            fr_locals = getargvalues(frame).locals
            # print(fr_locals.get('__qualname__'), '__qualname__' in fr_locals, func.__name__)

            try:
                bound2 = fr_locals["__qualname__"] is not None
            except KeyError:
                bound2 = False

        @wraps(func)
        async def wrapper(*args, **kw):
            instance = _resolve_instance(func, args, bound, bound2)
            await _async_handle_request(func, PARAMS, LOCKS, HISTORY, instance)

            return await func(*args, **kw)

        if _LIMITCALLS_STORE_GLOBALLY:
            _LIMITCALLS_PARAMS[wrapper] = PARAMS
            _LIMITCALLS_HISTORY[wrapper] = HISTORY

        return wrapper

    if f:
        return actual_decorator(f)

    return actual_decorator


def async_limitcalls_f(limit, interval=None, action="error", **kw):
    """For ordinary functions and classmethods/staticmethods,
    or if calls to method are not intended do be counted separately for each instance"""
    return async_limitcalls(limit, interval, action, bound=False, **kw)


def async_limitcalls_m(limit, interval=None, action="error", **kw):
    """For methods"""
    return async_limitcalls(limit, interval, action, bound=True, **kw)
