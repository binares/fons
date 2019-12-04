import abc
import multiprocessing
import asyncio
import functools
from functools import wraps
import inspect

from collections import deque
import numpy as np
import math
import copy
import platform
import warnings
import datetime
dt = datetime.datetime
td = datetime.timedelta

from fons.debug import wrap_trylog
import fons.log as _log
from fons.processes import LogiProcess
from fons.reg import create_name
from fons.threads import EliThread
import fons.time as fontime
from fons.errors import (
    QuitException, WaitException, TerminatedException,
    TickerException, TickerAlreadyAdded, AllTerminated,
    TickerQuitException, TickerWaitException, TickerTerminated
)
                    

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

LOGGING_LEVEL = 10
_PLATFORM = platform.system()
_TICKER_NAMES = set()
_ROUTINE_NAMES = set()


#Automatically assigns class attribute " _name" (= the name of class)
# if user has not specified the attribute itself
class _AddName(type):
    def __new__(cls, name, bases, attrs):
        newattrs = {'_name': name}
        newattrs.update(attrs)
            
        return super(_AddName, cls).__new__(cls, name, bases, newattrs)
    
    

def _to_td(value):
    if isinstance(value,td):
        return value
    elif isinstance(value,(int,float)):
        return td(seconds=value)
    else: raise TypeError(type(value))


def _verify_target(values, add_to=None, target_null=False):
    if add_to is None:
        add_to = {}
        
    if not len(values):
        raise ValueError('Target not given')
    
    target = values[0]
    
    if target_null and target is None: pass
    elif not hasattr(target,'__call__'):
        raise TypeError('Target is not callable: {}'.format(target))
    
    try: args = values[1]
    except IndexError: args = None
    
    if args is None: args = tuple()
    elif not hasattr(args,'__iter__'):
        raise TypeError('Args is not iterable: {}'.format(args))
    
    try: kwargs = values[2]
    except IndexError: kwargs = None
    
    if kwargs is None: kwargs = {}
    elif not isinstance(kwargs,dict):
        raise TypeError('Kwargs is not dict: {}'.format(kwargs))
    
    
    add_to['target'] = target
    add_to['args'] = args
    add_to['kwargs'] = kwargs
    
    
    return add_to


def _accepts_args(f):
    fas = inspect.getfullargspec(f)
    c_args = fas.args
    #inspect.ismethod is accurate whether or not "self" is first arg,
    # or if it only has *args
    if inspect.ismethod(f):
        c_args = c_args[1:]
    return len(c_args) > 0 or fas.varargs
    

def callback(f):
    @wraps(f)
    def wrapper(*args,**kw):
        self = args[0]
        callback = self._inf['callback']['target']
        accepts_arg = self._inf['callback']['accepts_arg']
        result = f(*args,**kw)
        
        if callback is not None:
            if accepts_arg:
                callback({'result': result, 'ticker': self, 'ts': dt.utcnow()})
            else: callback()
        
        return result
    
    return wrapper
    

def async_callback(f):
    @wraps(f)
    async def wrapper(*args,**kw):
        self = args[0]
        callback = self._inf['callback']['target']
        accepts_arg = self._inf['callback']['accepts_arg']
        result = await f(*args,**kw)
        
        if callback is None: pass
        elif self._inf['callback']['isCoro']:
            if accepts_arg: await callback({'result': result, 'ticker': self, 'ts': dt.utcnow()})
            else: await callback()
        else: 
            if accepts_arg: callback({'result': result, 'ticker': self, 'ts': dt.utcnow()})
            else: callback()
        
        return result
    
    return wrapper




#----------------------------------------------------------------------

class BaseTicker(metaclass=abc.ABCMeta):
    def __init__(self, *, callback=None, keepalive=None, name=None, logging_level=None):
        self._inf = copy.deepcopy(self._inf)
        self._ui = copy.deepcopy(self._ui)
        self._hidden = copy.deepcopy(self._hidden)
        
        self._inf['callback']['target'] = callback
        self._supers = set()
        
        if callback is not None:
            self._inf['callback']['accepts_arg'] = _accepts_args(callback)
            
        self._inf['keepalive'] = bool(isinstance(keepalive,dict) or keepalive)
        self._inf['keepalive_params'] = (dict({'attempts':True,'throw':TerminatedException},**keepalive) 
                if isinstance(keepalive,dict) else {'attempts':True,'throw':TerminatedException})
        if self._inf['keepalive']:
            self.loop = wrap_trylog(self.loop,**self._inf['keepalive_params'])
            
        self._hidden['closed'] = multiprocessing.Event()
        self._hidden['updated'] = multiprocessing.Event()
        self._hidden['lock'] = multiprocessing.Lock()
        
        if name is None and hasattr(self.__class__,'_name'):
            name = self.__class__._name
        self._name = create_name(name, default=self.__class__.__name__, registry=_TICKER_NAMES)
        
        self.logging_level = logging_level if logging_level is not None else LOGGING_LEVEL

    @abc.abstractmethod
    def tick(self, errors='raise', update_supers=True):
        pass
    
    @abc.abstractmethod
    def get_time_remaining(self):
        pass
    
    def __call__(self,*args,**kw):
        return self.tick(*args,**kw)
    
    def loop(self, update_supers=True):
        """Loops the tick method, with `errors` set to 'sleep'"""
        self._verify_is_open()
        tlogger.log(self.logging_level,'Starting ticker loop: {}'.format(self.name))
        try: 
            while True:
                try:
                    self.sleep()
                    self.tick(errors='sleep', update_supers=update_supers)
                except TerminatedException as e:
                    if self._closed: break
                    else: raise e
        finally:
            tlogger.log(self.logging_level,'Ticker loop ended: {}'.format(self.name))
    
    def _update_supers(self):
        for s in self._supers:
            s._update_timer(self,update_supers=True)
            
            
    def sleep(self, time='remaining'):
        t0 = time
        if isinstance(time,dict):
            t0,time = next(iter(time.items()))
        
        event = self._hidden['updated']
        lock = self._hidden['lock']
        tlogger0.log(self.logging_level,'Sleeping on ticker {} (time: {})'.format(self.name,time))
        try:
            while True:
                with lock:
                    self._verify_is_open()
                    if time == 'updated': 
                        time = None
                    elif time == 'remaining':
                        time = max(0, self.get_time_remaining())
                        event.clear()
                
                if event.wait(time):
                    event.clear()
                    self._verify_is_open()
                    time = t0
                    if time == 'remaining':
                        continue  
                break
        finally:
            tlogger0.log(self.logging_level,'Sleep ended: {}'.format(self.name))
       
    def close(self):
        tlogger.log(self.logging_level,'Closing ticker {}'.format(self.name))
        with self._hidden['lock']:
            if not self._closed:
                self._ui['time_closed'] = dt.utcnow()
                self._closed = True
                
            if not self._hidden['closed'].is_set():
                self._hidden['closed'].set()
            if not self._hidden['updated'].is_set():
                self._hidden['updated'].set()
            
            
    def _verify_is_open(self):
        if self._closed:
            raise TerminatedException('{} is closed'.format(self._name))
        return True
    
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self,value):
        self._name = value
    
    _inf = {'callback':{'target':None,'accepts_arg':None},'keepalive':False,'keepalive_params':{}}
    _ui = {'time_closed': None}
    _hidden = {'closed':None, 'updated': None, 'lock': None}
    _closed = False
    

class AsyncBaseTicker(BaseTicker):
    def __init__(self, *args, loop=None, **kw):
        super().__init__(*args,**kw)
        if loop is None: loop = asyncio.get_event_loop()
        self._inf['event_loop'] = loop
        self._hidden['closed'] = asyncio.Event(loop=loop)
        self._hidden['updated'] = asyncio.Event(loop=loop)
        #self._hidden['lock'] = asyncio.Lock()
        self._inf['callback']['isCoro'] = asyncio.iscoroutinefunction(self._inf['callback']['target'])
        

    async def __call__(self,*args,**kw):
        return await self.tick(*args,**kw)
        
        
    async def loop(self, update_supers=True):
        """Loops the tick method, with `errors` set to 'sleep'"""
        self._verify_is_open()
        tlogger.log(self.logging_level,'Starting ticker loop: {}'.format(self.name))
        try:
            while True:
                try: await self.tick(errors='sleep', update_supers=update_supers)
                except TerminatedException as e:
                    if self._closed: break
                    raise e
        finally:
            tlogger.log(self.logging_level,'Ticker loop ended: {}'.format(self.name))
    
    
    async def sleep(self, time='remaining'):
        t0 = time
        if isinstance(time,dict):
            t0 = next(iter(time))
            time = next(iter(time.values()))
            
        event = self._hidden['updated']
        lock = self._hidden['lock']
        loop = self._inf['event_loop']
        is_windows = _PLATFORM == 'Windows'
        tlogger0.log(self.logging_level,'Sleeping on ticker {} (time: {})'.format(self.name,time))
        try:
            while True:
                with lock:
                    self._verify_is_open()
                    if time == 'updated': 
                        time = None
                    elif time == 'remaining':
                        time = max(0, self.get_time_remaining())
                        event.clear()
                
                if time is not None and time <= 0:
                    break
                
                # Anything below 0.001 for non-windows and 0.016 for windows
                # may not be slept to the end.
                sleep_time = max(0.001, time)
                if is_windows:
                    sleep_time = max(0.016, time)
                
                try:
                    await asyncio.wait_for(event.wait(), sleep_time, loop=loop)
                    event.clear()
                    self._verify_is_open()
                    # Event was set. Break out.
                    if t0 != 'remaining':
                        break
                except asyncio.TimeoutError:
                    # We can't break out of the loop yet, as asyncio.sleep isn't completely accurate
                    pass
                finally:
                    time = t0
        finally:
            tlogger0.log(self.logging_level,'Sleep ended: {}'.format(self.name))

    async def close(self):
        super().close()
        
        
#############################################################################

class ScheduleTicker(BaseTicker):
    """For calling targetfunc in time restricted manner,
       .tick() or simply () attempts to call the target and return its output
       .loop() cycles the target endlessly
       .run() creates and runs a new thread with .loop as its target"""

    def __init__(self,target=None, interval=None,
                 sync=None, args=None, kwargs=None, *, 
                 delay=None, lock=None, keep=5,
                 errors='raise',return2=None, return2_call=False,
                 callback=None, keepalive=None, name=None, **kw):

        """
        Args [Optional]:
          target (func):
            target func

            
          interval (int,float,timedelta,Ticker,callable,list/tuple):
            tick interval
            --<td,int,float,str,DateOffset> -> fontime.freq_to_offset(interval)
            --<list/tuple> -> [callable, args, kw]
            if Ticker, its tick() must return interval
            if callable, must return interval
            
        
          sync (datetime, timedelta,int,float, str: 'first','epoch','epoch-delay','random','interval' / offset-like, Offset)):
            point in time which measures integer number of intervals passed;
            ::default: None
            --<timedelta,int,float,offset-like,DateOffset> -> <datetime || fontime.dt_round(dt.utcnow(), sync)>
            --<str>: 'epoch'  [epoch is the moment of tick() being called for the 1st time] 
                     'first'  [first = first_entry, guarantees t(2nd_tick()) - t(1st_tick()) = interval]
                     'random' [random point of time in tp: (dt_round(dt.utcnow(),interval), interval)]
                     'interval-<start>..<end>' [dt_round(dt.utcnow(), interval); [OPTIONAL] <start> / <end> floats in range(0,1)]
                     
                     
            if None, each entry is counted from the *end* of the last tick
             e.g if target takes unusually long, the interval will still be added on top of that
             --delay must be None
            otherwise each new entry is synced to the sync point
              entry = sync + n*interval  || [n E int] || entry < dt.utcnow()
            
            ( tick can be called if dt.utcnow() > last_entry + interval + delay )
                     
          
          args (listlike):
            target func args
          kwargs (dict):
            target func kwargs
                     
          ---------------------------           
          
          delay(timedelta,int,float, str: offset-like, Offset):
            if sync != None, this will be added to sync [next = last + interval + delay]
            --<timedelta,int,float,str,DateOffset> -> fontime.freq_to_offset(delay)

            

          
          lock (datetime, timedelta, float,int, str: 'next'/offset-like, Offset): 
            forbids updating until the given moment in datetime
            --<timedelta,int,float,offset-like,DateOffset> -> <datetime || dt.utcnow() + fontime.freq_to_offset(lock)>
            --<str>
              'next' - lock is synced to *next* tick() time from dt.utcnow()
                        [but sync param itself must be None or value (cannot be str variable)]
            ------------------------
          errors (str):
            'raise' - raise WaitError if tick is called prematurely
            'warn' - warn, and return return2
            'hide' - return return2
          return2 (obj):
            returned by tick() when errors == 'hide'/'warn'
          return2_call (bool):
            if True, then return2 is returned as return2()
             in that case return2 can be passed as [target2,args2,kwargs2]
          callback (function):
             a single-argument function to be called after each tick;
              argument to be passed: {"result": result, "ticker": ticker, "ts": timestamp}
          name (str,int):
            name of the Ticker instance, if int then added to the end of cls.__name__
         
        **kw
          return2_copy (bool, func):
            if True, the .return2() output will be deepcopied before returned
            if function, this function will be used to copy .return2() before returned
        """
        super().__init__(callback=callback, keepalive=keepalive, name=name, logging_level=kw.get('logging_level'))        
        
        if interval is None: self.interval = self._interval
        else: self.interval = interval
        
        interval = self._ui['interval']
        
        if sync is None: pass
        elif isinstance(sync,str):
            repl = sync.replace(' ','').lower()
            if repl.startswith('random'):
                range_part = repl[repl.find('-')+1:] if repl.find('-') != -1 else ''
                ddloc = range_part.find('..')
                to_float = lambda x,default: default if not len(x) else float(x)
                try: fa,fb = (0,1) if ddloc==-1 else ( to_float(range_part[:ddloc],0),to_float(range_part[ddloc+2:],1) )
                except Exception:
                    raise ValueError('Could not understand `sync`: {}'.format(sync))
                if fa < 0: raise ValueError('Sync `random` left endpoint must be >= 0; sync: {}'.format(sync))
                elif fb > 1: raise ValueError('Sync `random` right endpoint must be <= 1; sync: {}'.format(sync))
                elif fa > fb: raise ValueError('Sync `random` left endpoint must be <= right endpoint; sync: {}'.format(sync))
                t00 = fontime.dt_round(dt.utcnow(),interval)
                interval_td = (t00 + interval) - t00
                t0 = t00 + fa*interval_td
                t1 = t00 + fb*interval_td
                rand_td = (t1 - t0) * np.random.random(1)[0]
                self._ui['sync'] = t0 + rand_td
            elif repl == 'interval':
                self._ui['sync'] = fontime.dt_round(dt.utcnow(),interval)
            elif repl not in ('first','epoch','epoch-delay'):
                self._ui['sync'] = fontime.dt_round(dt.utcnow(),sync)#fontime.freq_to_td(sync, coerce=True)
            else: self._ui['sync'] = repl
        elif isinstance(sync, (td,float,int,fontime.offsets.DateOffset)) and not isinstance(sync,bool):
            self._ui['sync'] = fontime.dt_round(dt.utcnow(),sync)
        elif isinstance(sync, dt):
            self._ui['sync'] = sync
        else: raise TypeError(type(sync))

        if delay is not None:
            delay_ofs = fontime.freq_to_offset(delay)
            if self._ui['sync'] is None and delay_ofs.n:
                raise ValueError('sync must not be None if delay specified')
            self._ui['delay'] = delay_ofs


        d_target = self._inf['target']
        _verify_target([target,args,kwargs],add_to=d_target, target_null=True)
        

        if errors is None: pass
        elif not isinstance(errors,str):
            raise TypeError(type(errors))
        elif errors not in ('raise', 'warn', 'hide'):
            raise ValueError(errors)
        else: self._inf['errors'] = errors
        
        
        r2 = self._inf['return2']
        
        if return2_call is True:
            if isinstance(return2,(list,tuple)):
                _verify_target(return2,add_to=r2)
            else: _verify_target([return2],add_to=r2)            
        
        else: r2['value'] = return2
        
        r2_copy = kw.get('return2_copy')
        if r2_copy is None: pass
        elif isinstance(r2_copy,bool):
            r2['copy'] = r2_copy
        elif hasattr(copy,'__call__'):
            r2['copy'] = True
            r2['copyfunc'] = copy
        else: raise TypeError(type(r2_copy))

        
        if lock is not None: 
            self.lock = lock
 
        for k in ('entries','ticks','tick_ends','attempts'):
            self._ui[k] = deque(self._ui[k], maxlen=keep)

        
        tlogger.log(self.logging_level,'{} interval: {}'.format(self._name, self._ui['_interval_str']))
        
        if (self._inf['target']['target'] is None and 
            self.__class__.target is ScheduleTicker.target):
            warnings.warn('Ticker\'s initiated target is None, nor has the target method been '
                          'overriden, henceforth tick() will only return \'return2\'')



    def _is_tick_time(self):
        if self.get_time_remaining() > 0:
            return False
        return True


    def get_time_remaining(self, as_float=True):
        now = dt.utcnow()
        _ui = self._ui
        
        remaining_lock = _ui['lock'] - now
        try:
            remaining = (_ui['entries'][0] + _ui['interval'] + _ui['delay']) - now
        except IndexError:
            remaining = td(0)
        
        if as_float:
            remaining_lock = remaining_lock.total_seconds()
            remaining = remaining.total_seconds()

        return max(remaining_lock, remaining)
    
    
    def _synced(self, stamps):
        ui = self._ui
        sync, interval, delay = ui['sync'], ui['interval'], ui['delay']
        
        single = not hasattr(stamps,'__iter__')
        if single: stamps = [stamps]
        
        timestamps_synced = [
            fontime.dt_synced(x-delay,interval,sync) for x in stamps]
        

        if single:
            return timestamps_synced[0]
        
        return timestamps_synced
        
        
    
    def _ticktock_1st(self, now):
        _ui = self._ui
        _ui['epoch'] = now
        
        #later in _ticktock() will be assigned _ui['first'] =  _ui['entries'][0]
        # because if `sync` was not bound to epoch, 
        # the first = _ui['entries'][0] != now - _ui['delay'] due to sync difference

        if _ui['sync'] == 'first':
            _ui['sync'] = now - _ui['delay']
            
        elif _ui['sync'] == 'epoch':
            _ui['sync'] = _ui['epoch']
        
        elif _ui['sync'] == 'epoch-delay':
            _ui['sync'] = _ui['epoch'] - _ui['delay']
        
    
    
    def _ticktock(self):
        """Updates `last` and `actual_last` in the beginning of every *valid* tick,
           i.e only called after _is_tick_time() == True"""
        
        ui = self._ui
        now = dt.utcnow() 
        ui['ticks'].appendleft(now)
        
        if ui['sync'] is None:
            return
        
        
        counter = ui['counter']
        if not counter:
            self._ticktock_1st(now)
        
        
        entry = self._synced(now)
        ui['entries'].appendleft(entry)
        
        if not counter:
            ui['first'] = entry




    def _ticktock2(self):
        """Updates `last` and `actual_last` in the *end* of every valid tick,
           (i.e if _is_tick_time() == True and after target()/return2() completes),
           ONLY IF sync = None"""
        ui = self._ui
        
        now = dt.utcnow()
        self._ui['tick_ends'].appendleft(now)
        
        counter = ui['counter']
        ui['counter'] = counter +1
        
        if ui['sync'] is not None:
            return
        
        
        self._ui['entries'].appendleft(now)
    
        if not counter:
            ui['epoch'] = now
            ui['first'] = now
            



    def _interval_updating(self):
        iu = self._inf['interval_updating']
        if not iu['enabled']:
            return
        
        try:
            params = [iu['target'],iu['args'],iu['kwargs']]
            i0 = self._interval
            self.interval = params
            if self._interval != i0:
                logger.debug('{} new interval: {}'.format(self._name, self._ui['_interval_str']))
        except (WaitException, TerminatedException):
            return
        

    @callback
    def tick(self, force=False, errors=None, update_supers=True):
        """Does the "tick", i.e tries to call the target;
           if Ticker is closed, raises TerminatedException;
           elif force == True, target is called always;
           else checks if the time has arrived;
           
           if time has not arrived, handles `errors`:
             'error' - raises WaitException
             'warn' - warns and returns return2()
             'hide' - returns return2()
             'sleep' - sleeps until time has arrived, returns target()
             
           else returns .target()
           
           
           If .target() raises QuitException,
             closes (it)self
             returns QuitException.value if it has one,
                     else .return2()
             
             
           Note that QuitException raised from .return2 is not caught.
           """
        
        self._ui['attempts'].appendleft(dt.utcnow())
           
        self._verify_is_open()


        if errors is None:
            errors = self._inf['errors']
        
        
        if force is not True:
            remaining = self.get_time_remaining()
            
            if remaining <= 0: pass
            
            elif errors == 'hide': 
                return self.return2()
            
            elif errors == 'warn':
                logger.debug('{} skipping tick() - wait of {} needed'.format(self._name,math.ceil(remaining)))
                return self.return2()
            
            elif errors == 'sleep':
                self.sleep({'remaining': remaining})

            
            else: raise WaitException(remaining)
        

        #update timestamps
        self._ticktock()
    
    
        try:
            response = self.target()
            self._interval_updating()
        
        except QuitException as e:
            #if level > 0, then was raised by return2,
            # which is not allowed
            if e._level: raise e
            elif len(e.args): 
                response = e.args[0]
            else: response = self.return2()
            
            self.close()
            
        except WaitException as e:
            e._level += 1
            raise e
            
        finally:
            #update timestamps
            self._ticktock2()
            if update_supers:
                self._update_supers()
        
        return response
        
        
        

        
    def target(self):
        """Calling the target function, returning its output.
           This method may be overridden for custom use."""
        d = self._inf['target']
        target = d['target']
        
        if target is not None:
            return target(*d['args'],**d['kwargs'])
        
        try: return self.return2()
        except QuitException as e:
            e._level += 1
            raise e
    
    
    def return2(self):
        """Called from tick() if it determines _is_tick_time() == False, with `errors` 
           set to 'warn' or 'hide'; or from target() if target has not been set.
           This method may be overridden for custom use."""
        r2 = self._inf['return2']
        
        if r2['target']:
            value = r2['target'](*r2['args'],**r2['kwargs'])
        else: value = r2['value']
        
        if r2['copy']:
            #value = _copy(value)
            value = r2['copyfunc'](value)

        return value

    
    @property
    def entries(self):
        """tick_ends if sync = None, 
           else ticks (starts) synced."""
        return self._ui['entries']
    
    
    @property
    def records(self):
        """Previous tick times recorded right before .target() started and at tick end."""
        return list(zip(self._ui['ticks'], self._ui['tick_ends']))
    
            

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, value):
        _ui = self._ui
        #if interval is Ticker, it must be tickeable at this moment
        func = None
        
        if isinstance(value,(list,tuple)):
            d = _verify_target(value)
            value = d['target']
        else: d = {'target':None, 'args': tuple(), 'kwargs': {}}
        
        
        if hasattr(value, '__call__') and not isinstance(value,fontime.offsets.DateOffset):
            func = value
            
            if isinstance(func,ScheduleTicker):
                assert func._inf['errors'] == 'raise'
                
            value = func(*d['args'],**d['kwargs'])

        
        if value is None:
            value = 0
            
        ofs = fontime.freq_to_offset(value)

        if func is not None:
            self._inf['interval_updating']['enabled'] = True
        else: 
            self._inf['interval_updating']['enabled'] = False
            
        d['target'] = func
        self._inf['interval_updating'].update(d)
        
        
        _ui['interval'] = ofs
        try: _ui['_interval_str'] = ofs.freqstr
        except AttributeError:
            _ui['_interval_str'] = '?'
        
        self._interval = ofs
        
                
        #updating sync
        #(the first wait time will be == interval, but the next one'd be unknown, 
        # due to entries[0] being synced to the old sync point)
        if _ui['sync'] is not None and _ui['epoch'] is not None:
            _ui['sync'] = self.entries[0]
            
        
        self._update_supers()
        with self._hidden['lock']:  
            self._hidden['updated'].set()
        
        
        
    @property
    def lock(self):
        return self._ui['lock']
    
    @lock.setter
    def lock(self, value):
        _ui = self._ui
        
        if value is None:
            value = dt.utcfromtimestamp(0)
            
        elif isinstance(value, (int, float, td, fontime.offsets.DateOffset)):
            value = dt.utcnow() + fontime.freq_to_offset(value)
            
        elif isinstance(value,str):
            if value.lower() not in ('next',):
                value = dt.utcnow() + fontime.freq_to_offset(value)
            
            elif _ui['sync'] is None:
                try: value = self.entries[0] + _ui['interval']
                except IndexError: value = dt.utcnow() + _ui['interval']
                #raise ValueError('For the lock to be synced the sync must not be None')
            
            elif not isinstance(_ui['sync'], dt):
                raise ValueError('Sync is not initiated yet.')
            
            else:
                nearest_synced = self._synced(dt.utcnow())
                value = nearest_synced + _ui['interval'] + _ui['delay']
                
            
        elif not isinstance(value,dt):
            raise TypeError(type(value))
        
        _ui['lock'] = value
        
        self._update_supers()
        with self._hidden['lock']:
            self._hidden['updated'].set()
        
        
    
    def get_last(self,raw=False):
        if raw: return self._ui['records'][0][1]
        else: return self._ui['entries'][0]
    
    
    def get_next(self,adjusted=True):
        ui = self._ui
        if ui['sync'] is None:
            raise ValueError('Next cannot be estimated if sync = None')
        
        last = self.get_last()

        nxt = last + ui['interval']
        now = dt.utcnow()
        
        if adjusted:
            nxt_synced = self._synced(now)
            nxt = max(nxt_synced,nxt)
        
        return nxt
        
    
    def get_sleep_time(self):
        t = self.get_time_remaining(as_float=True)
        return max(0.0, t)
    
    @property
    def counter(self):
        return self._ui['counter']
    
    @property
    def args(self):
        return self._inf['target']['args']
    @args.setter
    def args(self, value):
        self._inf['target']['args'] = value
        
    @property
    def kwargs(self):
        return self._inf['target']['kwargs']
    @kwargs.setter
    def kwargs(self, value):
        self._inf['target']['kwargs'] = value
        

    _interval = 0
    
    _ui = {'interval': td(0), 'sync':None, 'delay': td(0),
           '_interval_str': '0S',
           'lock': dt.utcfromtimestamp(0),
           
           'attempts': deque(maxlen=5),
           'ticks': deque(maxlen=5),
           'tick_ends': deque(maxlen=5),
           'entries': deque(maxlen=5),
           
           'first': None, 'epoch': None, 'counter': 0, 
           'time_closed': None, }
    
    _inf = {'target': {'target': None, 'args': tuple(), 'kwargs': {}},
            'errors': 'raise',
            'return2': {'value': None, 'copy': False, 'copyfunc': copy.deepcopy,
                        'target':None, 'args':tuple(), 'kwargs':{}},
            'callback': {'target': None, 'accepts_arg':None},
            'keepalive': False, 'keepalive_params': {},
            'interval_updating': {'enabled': False, 'target': None, 'args': tuple(), 'kwargs': {}},}



class TPMethods:
    def start_thread(self, join=False, add_to=None, *, trylog=True, keepalive=False, loop=None, daemon=None):
        if self._thread is None:
            t = self.to_thread(loop=loop, trylog=trylog, keepalive=keepalive, daemon=daemon)
        else: t = self._thread
        
        if add_to is not None:
            add_to.append(t)
        
        t.start()
        
        if join: t.join()
        
        return t
    
    
    def to_thread(self, group=None, name=None, *, trylog=True, keepalive=False, loop=None, daemon=None):
        default =  '({})Thread'.format(self._name) \
                        if str(self._name)[-1:].isdigit() else \
                    '{}Thread'.format(self._name)
        new_name = create_name(name, default=default, add_int='if_taken')
        #Note that self.loop may already be wrapped in u_errors.trylog if `keepalive` was passed to __init__
        
        #if self._inf['keepalive'] is set (self.loop wrapped), then we don't want to extra wrap with trylog
        # unless specific instructions are passed
        if not self._inf['keepalive']: pass
        elif not (isinstance(trylog,dict) and len(trylog)):
            trylog=False
            
        if keepalive is True: keepalive = {'throw': TerminatedException}
        elif isinstance(keepalive,dict) and 'throw' not in keepalive:
            keepalive = dict(keepalive, throw=TerminatedException)
            
        t = EliThread(group=group, target=self.loop, loop=loop, name=new_name, daemon=daemon, trylog=trylog, keepalive=keepalive)
        self._thread = t
        
        return t
    

    def start_process(self, join=False, add_to=None):
        if self._process is None:
            t = self.to_process()
        else: t = self._process
        
        if add_to is not None:
            add_to.append(t)
        
        t.start()
        
        if join: t.join()
        
        return t
    
    
    def to_process(self, group=None, name=None, *, daemon=None):
        default =  '({})Process'.format(self._name) if str(self._name)[-1:].isdigit() else '{}Thread'.format(self._name)
        new_name = create_name(name, default=default, add_int='if_taken')
        
        t = LogiProcess(group=group, target=self.loop, name=new_name, daemon=daemon)
        
        self._process = t
        
        return t
    
    _thread = None
    _process = None
    


class Ticker(TPMethods, ScheduleTicker):
    pass
    


class AsyncTicker(AsyncBaseTicker, ScheduleTicker):
    def __init__(self,*args,loop=None,**kw):
        super().__init__(*args,loop=loop,**kw)
        self._inf['target']['isCoro'] = asyncio.iscoroutinefunction(self._inf['target']['target'])
        self._inf['return2']['isCoro'] = asyncio.iscoroutinefunction(self._inf['return2']['target'])
    
    
    @async_callback
    async def tick(self, force=False, errors=None, update_supers=True):
        """Does the "tick", i.e tries to call the target;
           if Ticker is closed, raises TerminatedException;
           elif force == True, target is called always;
           else checks if the time has arrived;
           
           if time has not arrived, handles `errors`:
             'error' - raises WaitException
             'warn' - warns and returns return2()
             'hide' - returns return2()
             'sleep' - sleeps until time has arrived, returns target()
             
           else returns .target()
           
           
           If .target() raises QuitException,
             closes (it)self
             returns QuitException.value if it has one,
                     else .return2()
             
             
           Note that QuitException raised from .return2 is not caught.
           """
        
        self._ui['attempts'].appendleft(dt.utcnow())
           
        self._verify_is_open()

        
        if errors is None:
            errors = self._inf['errors']
        
        
        if force is not True:
            remaining = self.get_time_remaining()
            
            if remaining <= 0: pass
            
            elif errors == 'hide': 
                return await self.return2()
            
            elif errors == 'warn':
                logger.debug('{} skipping tick() - wait of {} needed'.format(self._name,math.ceil(remaining)))
                return await self.return2()
            
            elif errors == 'sleep':
                await self.sleep({'remaining': remaining})
                
            else: raise WaitException(remaining)
        

        #update timestamps
        self._ticktock()
    
    
        try:
            response = await self.target()
            self._interval_updating()
        
        except QuitException as e:
            #if level > 0, then was raised by return2,
            # which is not allowed
            if e._level: raise e
            elif len(e.args): 
                response = e.args[0]
            else: response = await self.return2()
            
            await self.close()
            
        except WaitException as e:
            e._level += 1
            raise e
            
        finally:
            #update timestamps
            self._ticktock2()
            if update_supers:
                self._update_supers()


        return response
    

    async def target(self):
        """Calling the target function, returning its output.
           This method may be overridden for custom use."""
        d = self._inf['target']
        target = d['target']
        
        if target is None: pass
        elif d['isCoro']:
            return await target(*d['args'],**d['kwargs'])
        else:
            return target(*d['args'],**d['kwargs'])
        
        try: return await self.return2()
        except QuitException as e:
            e._level += 1
            raise e
        
    
    async def return2(self):
        """Called from tick() if it determines _is_tick_time() == False, with `errors` 
           set to 'warn' or 'hide'; or from target() if target has not been set.
           This method may be overridden for custom use."""
        r2 = self._inf['return2']
        
        if not r2['target']: 
            value = r2['value']
        elif r2['isCoro']:
            value = await r2['target'](*r2['args'],**r2['kwargs'])
        else:
            value = r2['target'](*r2['args'],**r2['kwargs'])

        
        if r2['copy']:
            #value = _copy(value)
            value = r2['copyfunc'](value)

        return value
    
    
################################################################    

class BaseTickManager(BaseTicker):
    def __init__(self, tickers, *, errors='raise', allterminated='sleep',
                 callback=None, keepalive=None, name=None, close_subs=False,
                 logging_level=None, gc_closed=True):
        """Its tick method ticks the next of its tickers"""
        super().__init__(callback=callback,keepalive=keepalive,name=name,logging_level=logging_level)
        
        if tickers is None: tickers = []
            
        self._tickers = {'open': [], 'closed': []}
        self._timer = {}

        for ticker in tickers:
            self.add_ticker(ticker)

        if errors is None: errors = 'raise'
        elif errors not in ('raise','sleep'):
            raise ValueError(errors)
        
        if allterminated is None: allterminated = 'sleep'
        elif allterminated not in ('sleep','raise','close'):
            raise ValueError(allterminated)

        
        self._inf['errors'] = errors 
        self._inf['allterminated'] = allterminated
        self._inf['close_subs'] = close_subs
        self._inf['gc_closed'] = gc_closed
        
        
    def add_ticker(self, ticker):
        if not isinstance(ticker,BaseTicker):
            raise TypeError('`ticker` must inherit from BaseTicker; got type: {}'.format(type(ticker)))
        elif ticker in self._tickers['open'] or ticker in self._tickers['closed']:
            raise TickerAlreadyAdded('Ticker {} has already been added to {}'.format(ticker._name, self._name))
        elif ticker._closed:
            raise TerminatedException('{} is closed. Cannot add to {}'.format(ticker._name,self._name))
        
        self._tickers['open'].append(ticker)
        ticker._supers.add(self)
        
        #this will also set self._hidden['updated'], 
        #causing AllTerminated 'sleep' mode to wake up (if allterminated was set to 'sleep'),
        #and also all parent tickers to wake up
        self._update_timer(ticker,True)
        
      
    @callback
    def tick(self, errors=None, update_supers=True):
        if errors is None:
            errors = self._inf['errors']
        
        while self._verify_is_open():
            self._remove_terminated()
            
            valid = (x for x in self._timer.items() if x[1] is not None)
            
            #AllTerminated will be raised only in the nth (highest) level manager's .tick
            # assuming that is the only one which's .tick is called
            # (the sub tickers' .tick called by nth's .tick are all guaranteed to be "valid")
            try: ticker,earliest = min(valid, key=lambda x: x[1])
            except ValueError:
                raise AllTerminated('{} - all tickers are terminated.'.format(self._name))
            
                
            time_remaining = earliest - dt.utcnow()
            secs = time_remaining.total_seconds()
            
            if secs > 0:
                if errors == 'sleep':
                    self.sleep(secs)
                    continue
                else: raise WaitException(secs)

            try: 
                ticker.tick(update_supers=update_supers)
                #self._update_timer(ticker, update_supers)
                break
            
            except AllTerminated as e:
                e._level += 1
                raise e
            
            except TerminatedException as e:
                if not e._level: 
                    continue
                e._level += 1
                raise e
        
        
    def loop(self, update_supers=True):
        self._verify_is_open()
        tlogger.log(self.logging_level,'Starting ticker loop: {}'.format(self.name))
        try:
            while True:
                try: self.tick(errors='sleep',update_supers=update_supers)
                except AllTerminated as e:
                    if e._level: raise e
                    try: self._handle_all_terminated()
                    except TerminatedException: break
                except TerminatedException as e:
                    if not e._level: break
                    else: raise e
        finally:
            tlogger.log(self.logging_level,'Ticker loop ended: {}'.format(self.name))
        

    def _remove_terminated(self):
        open = self._tickers['open']
        len_tickers = len(open)
        for i,ticker in enumerate(reversed(open)):
            if ticker._closed:
                del open[len_tickers-(i+1)]
                del self._timer[ticker]
                if not self._inf['gc_closed']:
                    self._tickers['closed'].append(ticker)
   
   
    def _handle_all_terminated(self):
        at = self._inf['allterminated']
        if at == 'raise':
            raise AllTerminated('{} - all tickers are terminated.'.format(self._name))
        elif at == 'close':
            self.close()
        else:
            self.sleep('updated')
   
        
    def _update_timer(self, ticker, update_supers=True):
        try: _next = ticker.get_time_remaining(as_float=False) + dt.utcnow()
        except AllTerminated:
            self._timer[ticker] = None
        else: self._timer[ticker] = _next
        
        with self._hidden['lock']:
            self._hidden['updated'].set()
        
        if update_supers:
            self._update_supers()
    
    
    def get_earliest(self):
        vals = (x for x in self._timer.values() if x is not None)
        try: return min(vals)
        except ValueError:
            raise AllTerminated('{} - all tickers are terminated'.format(self._name))
    
    def get_time_remaining(self, as_float=True):
        delta = self.get_earliest() - dt.utcnow()
        
        if as_float:
            return delta.total_seconds()
        return delta
        

class TickManager(TPMethods, BaseTickManager):
    def close(self):
        super().close()
        if self._inf['close_subs']:
            for t in self._tickers['open']:
                t.close()
        self._remove_terminated()


class AsyncTickManager(AsyncBaseTicker, BaseTickManager):
    def __init__(self,tickers,*, loop=None, allterminated='sleep', **kw):
        """Asynchronous version of TickManager."""
        super().__init__(None, loop=loop, allterminated=allterminated, **kw)
        
        self._hidden['queue'] = asyncio.Queue(loop=self._inf['event_loop'])

        if tickers is None:
            tickers = []
            
        for t in tickers:
            self.add_ticker(t)
        

    def add_ticker(self, ticker):
        if not isinstance(ticker,AsyncBaseTicker):
            raise TypeError('`ticker` must inherit from AsyncBaseTicker; got type: {}'.format(type(ticker)))
        TickManager.add_ticker(self, ticker)
        loop = self._inf['event_loop'] #ticker._inf['event_loop']
        async def put():
            await self._hidden['queue'].put(ticker)
            with self._hidden['lock']:
                self._hidden['updated'].set()
        f = functools.partial(asyncio.ensure_future, put(), loop=loop)
        loop.call_soon(f)
        
        
    async def _get_free_ticker(self):
        ticker = await self._hidden['queue'].get()
        
        if isinstance(ticker,QuitException):
            raise TerminatedException('{} is closed'.format(self._name))
        
        return ticker
    
    
    async def _tick_and_release(self, ticker, *args, **kw):
        try: 
            await ticker.tick(*args,**kw)
        except TerminatedException as e:
            #Note that .tick tries to remove any terminated tickers before calling ._tick_and_release, but sometimes
            # due to delay the ticker may close *in the meanwhile*, and due to .tick_and_release being called through
            # loop.call_soon() (not directly await .tick_and_release()), the exception shows up on the log
            #That's why decided *not* to raise the TerminatedException here
            """"e._level += 1
            raise e"""
            return
        else:
            callback = self._inf['callback']['target']
            if callback is None: pass
            elif self._inf['callback']['isCoro']:
                await callback({'result': None, 'ticker': self, 'ts': dt.utcnow()})
            else: callback({'result': None, 'ticker': self, 'ts': dt.utcnow()})
                
            #self._update_timer(ticker, False)
        finally:
            await self._hidden['queue'].put(ticker)
    
    
    async def tick(self, errors=NotImplemented, update_supers=True):
        while self._verify_is_open():
            self._remove_terminated()
            
            if not len(self._tickers['open']):
                await self._handle_all_terminated()
            
            ticker = await self._get_free_ticker()
            if ticker._closed:
                continue
            
            loop=self._inf['event_loop'] #ticker._inf['event_loop']
            coro = self._tick_and_release(ticker,errors='sleep',update_supers=update_supers)
            f = functools.partial(asyncio.ensure_future, coro, loop=loop)
            loop.call_soon(f)
            break
        
        
    async def loop(self, update_supers=True):
        """cours = (ticker.loop() for ticker in self._tickers['open'])
        await asyncio.gather(*cours, return_exceptions=True)"""
        self._verify_is_open()
        tlogger.log(self.logging_level,'Starting ticker loop: {}'.format(self.name))
        try:
            while True:
                try: await self.tick(update_supers=update_supers)
                except TerminatedException as e:
                    break
                    """if not e._level: break
                    else: raise e"""
                    #e._level is always 0, 
                    # because ticker.tick() in self.tick() does not raise
                """No AllTerminated is needed to be caught, 
                   as it is already handled in the tick"""
        finally:
            tlogger.log(self.logging_level,'Ticker loop ended: {}'.format(self.name))
    
    
    async def _handle_all_terminated(self):
        at = self._inf['allterminated']
        if at == 'raise':
            raise AllTerminated('{} - all tickers are terminated.'.format(self._name))
        elif at == 'close':
            await self.close()
        else:
            await self.sleep('updated')
            
            
    async def sleep(self, time=None):
        """This works but is not meant to be used with time=`None`,
           as calling get_time_remaining() will fail if no tickers are left"""
        await super().sleep(time)
        
            
    async def close(self):
        event = self._hidden['closed']
            
        if not event.is_set():
            await self._hidden['queue'].put(QuitException())
            
        await super().close()
        
        if self._inf['close_subs']:
            for t in self._tickers['open']:
                if isinstance(t,AsyncBaseTicker):
                    await t.close()
                else: t.close()
                
        self._remove_terminated()
        
        
    _hidden = {'closed': None, 'updated':None, 'lock': None, 'queue': None}
    


class Routine:
    def __init__(self, sched={}, tickmgr={}, *, name=None):
        self._locks = {-1: asyncio.Lock()}
        self._events = {}
        
        #this contains instructions for creating various tickers,
        #a dict *key* will later identify 
        # 1. its corresponding ticker in self._tickers ({key: resulting_ticker}),
        # 2. its corresponding event in self._events
        #a dict *value* will be used to create the ticker, and should be in the format 
        #{
        # target:method_name_or_function,
        # args:target_args,
        # kwargs:target_kwargs,
        # lock_id:None/<int>/<asyncio.Lock>
        # no_set_event_on: if target returns this value, event will not be set
        #  -- (NB! the comparison operator is `is` ("value is no_set_event_on"), therefore strings/ints/floats.. will not do)
        #  --defaults to False
        # ..all other arguments that can be passed to AsyncTicker.__init__
        #}
        # may be updated manually, calling self.sched.update({..}) in a subclass
        if not isinstance(sched,dict):
            raise TypeError(type(sched))
        self.sched = sched.copy()
        
        if name is None and hasattr(self.__class__,'_name'):
            name = self.__class__._name
        self._name = create_name(name, default=self.__class__.__name__, registry=_ROUTINE_NAMES)
        
        tcm = tickmgr.copy()
        if tcm.get('close_subs') is None:
            tcm['close_subs'] = True
        if 'tickers' not in tcm: tcm['tickers'] = []
        if tcm.get('name') is None: tcm['name'] = self.name + '-TickManager'
        
        self._tickmgr = AsyncTickManager(**tcm)
        self._tickers = {}
    
    
    def create_schedule(self):
        """Creates tickers out of .sched attribute.
        May also be called while Routine is already running (.start has been called)"""

        def wrap_callback(cb,event,**kw):
            #NB! _accpets_args must be called before wrapping to corotine
            # due to coroutine() replacing it with *args and **kw
            cb_is_set = cb is not None
            accepts_args = cb_is_set and _accepts_args(cb)
            iscoro = cb_is_set and asyncio.iscoroutinefunction(cb)
            """if not asyncio.iscoroutinefunction(cb):
                cb = asyncio.coroutine(cb)"""
            
            no_set_event_on = kw.get('no_set_event_on')
            if no_set_event_on is None: pass
            elif not hasattr(no_set_event_on,'__call__'):
                raise TypeError('`no_set_event_on` must be None or have attr "__call__"; got: {}'.format(no_set_event_on)) 
            
            async def set_event(*args):
                #ticker @callback passes {'result': , 'ticker': ,'ts': }
                #print(cb_is_set,set_event_on,args[0]['result'],set_event_on(args[0]['result']))
                if no_set_event_on is None or not no_set_event_on(args[0]['result']):
                    event.set()
                if not cb_is_set: pass
                elif accepts_args:
                    if not iscoro: cb(*args)
                    else: await cb(*args)
                else:
                    if not iscoro: cb()
                    else: await cb()

            return set_event
        
        logger.debug('{} - creating schedule'.format(self.name))
        max_lock_id = max(self._locks)
        for n,params in self.sched.items():
            #Only new schedule items will be added
            #If want remove from schedule, call .remove(name)
            if n in self._tickers: continue
            lock_id = params.get('lock_id')
            if isinstance(lock_id,asyncio.Lock):
                try: lock_id = next(x for x,y in self._locks.items() if lock_id is y)
                except StopIteration:
                    max_lock_id = max_lock_id + 1
                    self._locks[max_lock_id] = lock_id
                    lock_id = max_lock_id   
            elif lock_id is None: 
                lock_id = max_lock_id = max_lock_id + 1

            if not isinstance(lock_id,int): 
                raise TypeError(type(lock_id))
            elif lock_id not in self._locks:
                max_lock_id = max(max_lock_id,lock_id)
                self._locks[lock_id] = asyncio.Lock()

            targkw = [params.get(p) for p in ('target','args','kwargs')]
            rout_kw = {'lock_id': lock_id}
            tickConfig = {x:y for x,y in params.items() if x not in ('target','args','kwargs','lock_id','no_set_event_on')} 
            
            self._events[n] = event = asyncio.Event()
            
            cb = tickConfig.get('callback')
            nseo = {x:y for x,y in params.items() if x=='no_set_event_on'}
            tickConfig['callback'] = wrap_callback(cb,event,**nseo)
            if tickConfig.get('name') is None:
                tickConfig['name'] = '{}-{}-Ticker'.format(self.name,n)

            ticker = AsyncTicker(self._routine, args=targkw, kwargs=rout_kw, **tickConfig)
            self._tickmgr.add_ticker(ticker)
            self._tickers[n] = ticker
    
    
    async def start(self):
        self._tickmgr._verify_is_open()
        self.create_schedule()
        logger.debug('Starting routine {}'.format(self.name))
        try: await self._tickmgr.loop()
        finally: tlogger.debug('Routine ended: {}'.format(self.name))
    
    
    async def _routine(self, target, args, kwargs, lock_id):
        if args is None: args = tuple()
        if kwargs is None: kwargs = {}
        method = getattr(self, target) if isinstance(target,str) else target
        
        lock = self._locks[lock_id]
        
        with await lock:
            if asyncio.iscoroutinefunction(method):
                return await method(*args,**kwargs)
            else:
                return method(*args,**kwargs)
    
    
    async def remove(self,name,from_sched=True):
        lock_id = self.get_lock_id(name)
        await self.get_ticker(name).close()
        del self._tickers[name]
        del self._events[name]
        if lock_id != -1 and not any(self.get_lock_id(n) == lock_id for n in self._tickers):
            del self._locks[lock_id]
        if from_sched and name in self.sched:
            del self.sched[name]
        #Note that removing all tickers will not cause the running tickmgr to stop,
        # unless .__init__(..,tickmgr={'allterminated':'close'}) was passed
    
    
    async def close(self):
        await self._tickmgr.close()
    
    
    def get_ticker(self,name):
        return self._tickers[name]
    
    def get_event(self,name):
        return self._events[name]
    
    def get_lock(self,id):
        if isinstance(id,str):
            id = self.get_lock_id(id)
        elif not isinstance(id,int):
            raise TypeError(type(id))
        return self._locks[id]
    
    def get_lock_id(self,name):
        return self.get_ticker(name)._inf['target']['kwargs']['lock_id']
        
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self,value):
        self._name = value
