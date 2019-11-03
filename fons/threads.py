import datetime
dt = datetime.datetime
td = datetime.timedelta
import time
import threading
import asyncio

import fons.debug as debug
from fons.errors import ThreadEndException
#from fons.reg import create_name

_THREAD_NAMES = set()


class Eli(type):
    def __new__(cls, name, bases, attrs):
        def wrap_run(f):
            def set_event_loop(self):
                loop = getattr(self,'_loop',None)
                if loop is None: self._loop = loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return f(self)
            return set_event_loop
        
        if not any(issubclass(x,threading.Thread) for x in bases):
            raise TypeError("class '{}' must be a subclass of 'threading.Thread'".format(name))
          
        if 'run' in attrs:
            attrs['run'] = wrap_run(attrs['run'])
        elif not any(issubclass(type(x),Eli) for x in bases):
            attrs['run'] = wrap_run(threading.Thread.run)
            
        return super(Eli, cls).__new__(cls, name, bases, attrs)
    
    
class EliThread(threading.Thread, metaclass=Eli):
    """Sets up event loop in the resulting thread. Integrates trylog."""
    def __init__(self, group=None, target=None, name=None, args=None, kwargs=None, *,
                 loop=None, trylog=True, keepalive=False, daemon=None):
        if args is None: args = ()
        if kwargs is None: kwargs = {}
        self._loop = loop if loop is not None else asyncio.new_event_loop()
        self._keepalive = bool(isinstance(keepalive,dict) or keepalive)
        self._trylog =  bool(isinstance(trylog,dict) or trylog)
        if not isinstance(trylog,dict): trylog = {}
        if not isinstance(keepalive,dict): keepalive = {}
        self._trylog_params = dict({'attempts':True},**keepalive) if self._keepalive else trylog
        
        if self._keepalive or self._trylog:
            args = (target,args,kwargs)
            kwargs = self._trylog_params
            target = debug.trylog
        #print('group: {}, target:{}, daemon: {}'.format(group,target,daemon))
        super().__init__(group, target, name, args, kwargs, daemon=daemon)


#-------------------------------

class LoopingThread(EliThread):
    def __init__(self, id, name, delay=None, absolute_delay=True, *, loop=None):
        super().__init__(loop=loop)
        self.id = id
        self.name = name
        
        if delay is not None:
            self._delay = {'period': delay, 'absolute': absolute_delay}
        else: self._delay = {'period': 0, 'absolute': absolute_delay}
        
        self._times = dict.fromkeys(['start','next','end'])

    
    def __init2__(self,_MyThread=[],**kw):
        values = []
        names = ['id','name','delay','absolute_delay']
        
        args_missed = 0
        
        for i,n in enumerate(names):
            if kw.get(n) is not None:
                values.append(kw.get(n))
                args_missed += 1
                del kw[n]
            elif 0 <= i-args_missed < len(_MyThread) and _MyThread[i-args_missed] is not None:
                values.append(_MyThread[i-args_missed])
            else: values.append(self._base_values[i])
        
        LoopingThread.__init__(self,*values,**kw)
        
        
    def startinfo(self):
        print("Starting " + self.name)
        ts = dt.utcnow()
        
        if self._times['start'] is None:
            self._times['start'] = ts
    
    #In case of relative delay, updates the time before which the next cycle is not allowed to start
    def update(self):
        if not self._delay['absolute']:
            ts = dt.utcnow()
            self._times['next'] = ts + self._delay['period']
            
    def do_this(self):
        pass
    
    def delay(self):
        ts = dt.utcnow()
        
        if not self._delay['absolute']:
            remaining = ts - self._times['next']
            
            if remaining > td(0):
                time.sleep(remaining)
                
        elif self._delay['period']:
            time.sleep(self._delay['period'])
    
    
    def run(self):
        self._set_event_loop()
        self.startinfo()

        while True:
            self.update()
            try:
                self.do_this()
            except ThreadEndException:
                self._shutdown = True
                
            if self._shutdown:
                return
            self.delay()

            
    _base_values = [1,"LoopingThread",None,True]
    _shutdown = False
            


if __name__ == '__main__':
    class A(threading.Thread, metaclass=Eli): pass
    class B(A): pass
    print(A.run,type(A))
    print(B.run,type(B))

    class T(EliThread):
        def run(self):
            print('get_loop: {}, loop: {}'.format(id(asyncio.get_event_loop()),id(self._loop)))
    t = T(loop=asyncio.new_event_loop())
    t.start()
    
    l = asyncio.get_event_loop()
    print(id(l))
    t2 = EliThread(target=lambda: print(id(asyncio.get_event_loop())), loop=l)
    t2.start()
    
