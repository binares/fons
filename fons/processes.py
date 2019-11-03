import time
import multiprocessing
from multiprocessing import Process as _Process

import fons.log as _log

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)


class Logi(type):
    def __new__(cls, name, bases, attrs):        
        def wrap_run(f):
            def init_logging(self):
                _log.standard_mp_logging(**self._log_params)
                return f(self)
            return init_logging
        
        def wrap_start(f):
            def start_loglisten(self):
                lp = getattr(self,'_log_params',None)
                if lp is None: self._log_params = lp = _log._globals.copy()
                #(if has already been started then ignores)
                _log.start_listener()
                return f(self)
            return start_loglisten
        
        if not any(issubclass(x,_Process) for x in bases):
            raise TypeError("class '{}' must be a subclass of 'multiprocessing.Process'".format(name))
        
        if 'run' in attrs:
            attrs['run'] = wrap_run(attrs['run'])
        elif not any(issubclass(type(x),Logi) for x in bases):
            attrs['run'] = wrap_run(_Process.run)
            
        if 'start' in attrs:
            attrs['start'] = wrap_start(attrs['start'])
        elif not any(issubclass(type(x),Logi) for x in bases):
            attrs['start'] = wrap_start(_Process.start)
        
            
        return super(Logi, cls).__new__(cls, name, bases, attrs)
    
    
class LogiProcess(_Process, metaclass=Logi):
    """Starts LogListener in child process with the QueueHandler from parent process"""
    def __init__(self, *args, log_params=None, **kw):
        super().__init__(*args,**kw)
        self._log_params = log_params.copy() if log_params is not None else _log._globals.copy()
        
        
class TkLogiProcess(_Process, metaclass=Logi):
    def __init__(self, nb, *args, log_params=None, **kw):
        """nb - tkinter.ttk.NoteBook object"""
        super().__init__(*args,**kw)
        self._log_params = log_params.copy() if log_params is not None else _log._globals.copy()
        
        if self.name not in _log._tklogiprocesses:
            _log.init_tab(nb,self.name)


    """def __del__(self):
        try: u_log._tklogiprocesses.remove(self.name)
        except KeyError: pass
        super().__del__()"""
        

def pool_processes(processes, max_concurrent=None, timeout=None, interval=0.05):
    if max_concurrent is None:
        max_concurrent = max(1, multiprocessing.cpu_count()-1)
    p_iter = iter(processes)
    running = []
    started = {}
    #print('max_concurrent: {}'.format(max_concurrent))
    while True:
        for p in running:
            if not p.is_alive(): pass
            elif timeout is not None and time.time()-started[p] > timeout:
                logger.debug('Process "{}" (pid: {}) has exceeded its timeout. Terminating.'.format(p.name,p.pid))
                try: p.terminate()
                except Exception as e:
                    logger2.error('Could not terminate process: {} (pid: {})'.format(p.name,p.pid))
                    logger.exception(e)
        running = [p for p in running if p.is_alive()]
        if len(running) >= max_concurrent:
            time.sleep(interval)
            continue
        try: p = next(p_iter)
        except StopIteration: break
        #print('p: {}'.format(p))
        started[p] = time.time()
        p.start()
        running.append(p)
    #print('running: {}'.format(running))
    [p.join() for p in running]
