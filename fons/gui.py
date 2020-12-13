"""
Make sure you have tkinter installed before using the features of this module.
`sudo apt-get install python3-tk`
"""
import json
from copy import deepcopy
from collections import OrderedDict
import multiprocessing
import time
import sys
import shlex

from fons.dict_ops import deep_update
from fons.errors import QuitException
from fons.io import update_settings, _META_NORM
from fons.log import (get_standard_5, init_tab, standard_logging)
from fons.processes import TkLogiProcess
from fons.py import rreload
from fons.sched import Ticker
from fons.threads import EliThread


NON_RESPONSIVE = ('debug*','info*','warning*','error*','critical*','main')
RRELOAD_BUTTON = False

logger,logger2,tlogger,tloggers,tlogger0 = get_standard_5(__name__)


def get_default_CFG(processes, dtypes=None):
    _process = {
        '_type_': dict,
        'default_dtype': None,
        'dtypes': {
            'target': {'_type_': str},
            'args': list,
            'kwargs': dict,
            'argv': {'_type_': (str, list), '_defval_': None},
            'conn': bool,
            'start': bool,
        }
    }
    if dtypes is None:
        dtypes = {}
    return {
        '_type_': dict,
        'default_dtype': None,
        'dtypes': {
           'processes': {
               '_type_': dict,
               # 'keys': list(processes),
               'unit': _process
            },
            '__meta__': deepcopy(_META_NORM),
            **dtypes,
        }
    }


class NbGUI:
    """Notebook styled gui"""
    def __init__(self, config={}):
        import tkinter as tk
        import tkinter.ttk as ttk
        
        self.root = tk.Tk()
        self.root.geometry('975x475')
        #self.root.resizable(0, 0)
        
        if config.get('title') is not None:
            self.root.title(config['title'])
        
        left_frame = tk.Frame(self.root)
        left_frame.pack(side=tk.LEFT)
        buttons_frame = tk.Frame(left_frame)
        buttons_frame.pack()
        entries_frame = tk.Frame(left_frame)
        entries_frame.pack(pady=(10, 0))
        
        self.nb = ttk.Notebook(self.root)
        #self.nb.grid(row=1, column=0, columnspan=50, rowspan=49, sticky='NESW')
        #self.nb.pack_propagate(0) 
        self.nb.pack(side=tk.LEFT, fill='both', expand=True)
        
        self.tabs = []
        self.tab_selected = None
        self.variables = {}
        self.values = {} # by (tab_name, var_name)
        self.default_values = {} # by var_name
            
        buttons = config.get('buttons')
        if buttons is None: buttons = {}
        for button_name, specs in buttons.items():
            callback = self.wrap_button(specs['command']) if specs.get('command') else None
            text = specs.get('text')
            b = tk.Button(buttons_frame, text=text, command=callback)
            b.pack()
        
        entries = config.get('entries')
        if entries is None: entries = {}
        for var_name, specs in entries.items():
            label = specs.get('label')
            width = specs['width'] if specs.get('width') else 12
            self.default_values[var_name] = value = specs['value'] if specs.get('value') else ''
            ef = tk.Frame(entries_frame)
            ef.pack()
            if label:
                tk.Label(ef, text=label).pack(side=tk.LEFT)
            self.variables[var_name] = var = tk.StringVar(value=value)
            tk.Entry(ef, textvariable=var, width=width).pack(side=tk.LEFT)
        
        tabs = _tabs = config.get('tabs')
        if tabs is None: tabs = {}
        elif not isinstance(tabs, dict):
            tabs = {}
            for item in _tabs:
                if isinstance(item, dict):
                    tab_name, specs = item['text'], item
                else:
                    tab_name, specs = item, {}
                tabs[tab_name] = specs
        
        for tab_name, specs in tabs.items():
            values = specs.get('values') # by var_name
            if values is None:
                values = {}
            elif isinstance(values, str):
                values = dict.fromkeys(self.variables, values)
            self.add_new_tab(tab_name, values)
    
    
    def add_new_tab(self, tab, variable_values={}):
        if tab in self.tabs:
            return
        self.tabs.append(tab)
        init_tab(self.nb, tab)
        for var_name in self.variables:
            value = variable_values.get(tab)
            if value is None:
                value = self.default_values[var_name]
            self.values[(tab, var_name)] = value
    
    
    def refresh(self, recursive=False):
        tab_selected = self.nb.tab(self.nb.select(), 'text')
        if self.tab_selected != tab_selected:
            for var_name, variable in self.variables.items():
                value = self.values.get((tab_selected, var_name))
                if value is None:
                    value = ''
                variable.set(value)
            self.tab_selected = tab_selected
        
        for var_name, variable in self.variables.items():
            self.values[(tab_selected, var_name)] = variable.get()
        
        if recursive:
            self.root.after(recursive, self.refresh, recursive)
    
    
    def wrap_button(self, f):
        def on_button(*args,**kw):
            tab_selected = self.nb.tab(self.nb.select(), 'text')
            return f(tab_selected, *args, **kw)
        return on_button


class TkThread(EliThread):
    def __init__(self, config, *args, **kw):
        super().__init__(*args,**kw)
        self.config = config
        self.start()
    
    def run(self):
        """It is important that the gui is initiated inside the running thread"""
        self.gui = NbGUI(self.config)
        self.gui.refresh(recursive=300)
        self.gui.root.mainloop()


def ignore(f):
    def check_ignore(*args,**kw):
        try: name = args[1] # (0 = self)
        except IndexError:
            name = kw['name']
        if name not in NON_RESPONSIVE:
            return f(*args,**kw)
    return check_ignore


class TkLogiProcessComplex:
    def __init__(self, processes={}, *, settings_path=None, cfg=None, CFG=None,
                 functions={}, title='TkLogiProcessComplex', termination_time=60, main_termination_time=75,
                 logging_dir=None, dpath=None, rreload_button=None):
        """
        :type processes: dict
            {
                process_name: {
                    target: function,
                    args: (...),
                    kwargs: {...},
                    argv: 'put something here',      # can also be list ['put', 'something', 'here'] 
                    conn: <bool>,                    # if True then function must accept `conn` as keyword (Pipe)
                    start: <bool>                    # whether or not it is started on .start
                }
            }
        about function:
            may accept `argv` as keyword, should default to sys.argv
            may accept `conn` as keyword
        about conn (Pipe):
            assumed to expect `None` as a cue to end itself (the function)
            assumed to send `None` back when done
        :type cfg: dict
            initial contents of the file located at `settings_path`
            cfg['processes'] is used to periodically deep update `self.processes`
            { processes: processes }                 # where processes are equivalent to `processes` argument
        """
        self.processes = dict(processes)
        self.verify_processes(self.processes)
        self.settings_path = settings_path
        self.cfg = deepcopy(cfg) if cfg is not None else {}
        self.CFG = deepcopy(CFG) if CFG is not None else {}
        self.functions = dict(functions)
        self.title = title
        self.termination_time = termination_time
        self.main_termination_time = main_termination_time
        self.logging_dir = logging_dir
        self.dpath = dpath
        self.rreload_button = rreload_button if rreload_button is not None else RRELOAD_BUTTON
        
        self.init_CFG()
        
        self._processes = {}
        self._exit = None
        self._cfg_updater = None
        self._gui_thread = None
        self._gui = None
        self._nb = None
        self._response_waiter = None
    
    
    @staticmethod
    def verify_processes(processes):
        for name in processes:
            if name in ('MainProcess', 'main'):
                raise ValueError("Processname '{}' is not allowed".format(name))
    
    
    def init_CFG(self):
        self.CFG = deep_update(get_default_CFG(self.processes), self.CFG, copy=True)
    
    
    def update_settings(self, add_new_process_tabs=False):
        old_processes = self.cfg.get('processes', {})
        c = self.cfg.get('__meta__', {}).get('counter', 0)
        update_settings(self.settings_path, self.cfg, self.CFG)
        c2 = self.cfg['__meta__']['counter']
        
        if not c or c2 > c:
            # update_settings doesn't deep_update automatically
            self.cfg['processes'] = deep_update(old_processes, self.cfg.get('processes', {}))
            cfg_processes = self.cfg['processes']
            if isinstance(cfg_processes, dict):
                self.verify_processes(cfg_processes)
                for p in cfg_processes:
                    if p in self.processes:
                        self.processes[p].update(cfg_processes[p])
                    else:
                        self.processes[p] = dict(cfg_processes[p])
        
        if add_new_process_tabs:
            for p in self.processes:
                if p not in self._gui.tabs:
                    self._gui.root.after(1, self._gui.add_new_tab, p)
    
    
    def init_process(self, name):
        specs = self.processes[name]
        target = specs['target']
        
        if target is None:
            target = name
        
        if isinstance(target, str):
            target = self.functions[target]
        
        argv = self._gui.values.get((name, 'argv'))
        if not argv:
            argv = specs.get('argv')
        
        if argv is None: pass
        elif isinstance(argv, str):
            argv = [''] + shlex.split(argv)
        else:
            argv = [''] + list(argv)
        
        conn = multiprocessing.Pipe() if specs.get('conn') else None
        
        args = tuple(specs['args']) if specs.get('args') is not None else ()
        kwargs = dict(specs['kwargs']) if specs.get('kwargs') is not None else {}
        if argv:
            kwargs['argv'] = argv
        if conn is not None:
            kwargs['conn'] = conn[1]
        
        p = TkLogiProcess(self._nb,
                          target=target,
                          args=args,
                          kwargs=kwargs,
                          name=name,
                          daemon=specs.get('daemon', False)) # this should be False, as it may spawn children
        self._processes[name] = {'p': p, 'conn': conn, 'args': args,
                                 'kwargs': kwargs, 'start': None, 'close': None,}
        return p
    
    def del_process(self, name):
        old = self._processes.get(name)
        if not old: return
        conn = old['conn']
        if conn:
            conn[0].close()
            conn[1].close()
        self._processes[name] = {}
    
    
    def _check_is_not_running(self, name):
        if not self._processes.get(name, {}).get('p'): pass
        elif self._processes[name]['p'].is_alive():
            logger2.error('Cannot start `{}`: is already running'.format(name))
            return False
        else:
            self.del_process(name)
        return True
    
    @ignore
    def start_process(self, name):
        if not self._check_is_not_running(name):
            return
        p = self.init_process(name)
        _p = self._processes[name]
        args_sfx = ' :: {}'.format(_p['args']) if _p['args'] else ''
        kw_sfx = ' :: {}'.format(_p['kwargs']) if _p['kwargs'] else ''
        logger2.info('Starting `{}`{}{}'.format(name, args_sfx, kw_sfx))
        self._processes[name]['start'] = time.time()
        p.start()
        logger2.info('Starting of `{}` (pid: {}) successful'.format(name, p.pid))
    
    @ignore
    def start_rl(self, name):
        if not self._check_is_not_running(name):
            return 
        logger2.info('Attempting to reload `{}` modules'.format(name))
        f = f0 = self.processes[name].get('target')
        if f is None:
            f = f0 = name
        if isinstance(f, str):
            f = self.functions[f]
        module = sys.modules[f.__module__]
        rreload(module)
        f = getattr(module, f.__name__)
        if isinstance(f0, str):
            self.functions[f0] = f
        else:
            self.processes[name]['target'] = f
        self.start_process(name)
    
    @ignore 
    def restart_process(self, name):
        logger2.info('Attempting to restart `{}`'.format(name))
        self.stop_process(name)
        self.start_process(name)
    
    
    @ignore
    def stop_process(self, name):
        try: p = self._processes[name]['p']
        except KeyError:
            logger2.error('Cannot stop `{}`: has not been initiated'.format(name))
            return
        if self._processes[name]['close']:
            logger2.error('`{}` is already waiting for termination.'.format(name))
            return
        if not p.is_alive():
            logger2.error('Cannot stop `{}`: is not running'.format(name))
            return
        logger2.info('Scheduling `{}` for termination'.format(name))
        self._processes[name]['close'] = time.time()
        conn = self._processes[name]['conn']
        if conn:
            conn[0].send(None)
        else:
            self.force_terminate_process(name)
    
    
    def force_terminate_process(self, name):
        p = self._processes[name]['p']
        logger2.info('Force terminating `{}`'.format(name))
        p.terminate()
        self.del_process(name)
    
    
    def _wait_on_responses(self):
        all_closed = True
        for name,d in self._processes.copy().items():
            p = d.get('p')
            conn = d.get('conn')
            start = d.get('start')
            close = d.get('close')
            updated = conn and conn[0].poll(0.01)
            if not updated:
                if not start or time.time() - start < 2:
                    pass
                elif not p.is_alive():
                    logger2.info('`{}` has terminated.'.format(name))
                    self.del_process(name)
                elif close and time.time() - close > self.termination_time:
                    logger2.info('`{}` has exceeded its allocated termination time. Force terminating.'.format(name))
                    self.force_terminate_process(name)
                else:
                    all_closed = False
                continue
            
            r = conn[0].recv()
            logger2.info('Received from {}\'s conn: {}'.format(name, r))
            if r is None:
                logger2.info('Process `{}` has successfully terminated itself.'.format(name))
                time.sleep(1)
                if p.is_alive():
                    logger2.error('But `{}` is till alive. Attempting force termination.'.format(name))
                    try: self.force_terminate_process(name)
                    except Exception as e:
                        logger2.exception(e)
                        all_closed = False
                        continue
                    time.sleep(0.5)
                self.del_process(name)
        
        if self._exit and all_closed:
            logger2.info('All subprocesses successfully closed. Exiting main.')
            raise QuitException
        elif self._exit and time.time() - self._exit > self.main_termination_time:
            logger2.error('Some processes could not be closed. Exiting main.')
            raise QuitException
    
    
    def exit(self, *args):
        if self._exit:
            logger2.error('Exit has already been scheduled.')
            return
        for n,d in self._processes.items():
            if not d: continue
            self.stop_process(n)
        self._exit = time.time()
    
    
    def start(self):
        buttons = [
            # ['restart', {'text': '|', 'command': self.restart_process}],
            ['stop', {'text': 'OFF', 'command': self.stop_process}],
            ['start', {'text': 'ON', 'command': self.start_process}],
            ['exit', {'text': 'EXIT', 'command': self.exit}],
        ]
        if self.rreload_button:
            buttons.insert(2, ['start-rl', {'text': 'ON-rl', 'command': self.start_rl}])
        
        config = {
            'title': self.title,
            'tabs': ['MainProcess'] + list(self.processes),
            #'tabs': ['debug*','MainProcess'] + list(self.processes),
            'buttons': OrderedDict(buttons),
            'entries': OrderedDict([
                ['argv', {'label': 'argv'}], #'width': 10
            ]),
        }
        
        self._gui_thread = TkThread(config, daemon=True)
        _started = time.time()
        while getattr(self._gui_thread, 'gui', None) is None and time.time() - _started < 5: # wait till _gui_thread starts
            time.sleep(0.05)
        self._gui = self._gui_thread.gui
        self._nb = self._gui_thread.gui.nb
        if self.settings_path:
            try: self.update_settings(True)
            except FileNotFoundError:
                with open(self.settings_path, 'w', encoding='utf-8') as f:
                    json.dump(self.cfg, f)
        
        standard_logging(dir=self.logging_dir, f_ending=self.title, dpath=self.dpath)
        start_by_default = [name for name, specs in self.processes.items() if specs.get('start')]
        
        for p in self.processes:
            self._gui.root.after(1, self._gui.add_new_tab, p)
        time.sleep(0.2)
        
        for name in start_by_default:
            self.start_process(name)
        
        if self.settings_path:
            self._cfg_updater = Ticker(self.update_settings, lambda: self.cfg['__meta__'].get('interval', 1),
                                       args=(True,), keepalive={'pause': 30}, name='MainProcess-cfgUpdater')
            self._cfg_updater.start_thread()
        
        self._response_waiter = Ticker(self._wait_on_responses, 1, name='ProcessListener')
        self._response_waiter.loop()
        if self._cfg_updater:
            self._cfg_updater.close()
        logger2.info('Closing Tkinter window.')
        self._gui_thread.gui.root.quit()
        #log.gui.root.destroy()
        time.sleep(1.5)
        logger2.info('`{}` terminated'.format(self.title))
