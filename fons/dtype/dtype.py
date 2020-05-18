import pandas as pd
import inspect
import datetime
dt = datetime.datetime
td = datetime.timedelta

import fons.log as _log
import fons.math.series as du
from fons.processes import LogiProcess
from fons.reg import create_name
from fons.sched import Routine
from fons.time import (dt_round, freq_to_offset)
from fons.verify import (init_data, verify_data)

from . import store
from . import merging

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

_MERGER_NAMES = set()


class DType(Routine):
    
    guts = None
    template = None
    id_attrs = []
    set_id_attrs = False # if True, `for a in self.id_attrs: setattr(self, a, id[a])` is called
    time_key = None
    time_freq = None
    storable = True
    merger_cls = None
    save_freq = '1T'
    ftype = None
    root = None
    file_fmt = None
    dir_fmt = None
    init_data = False
    index_col = None # For reading dataframe
    index_dtype = None # For reading dataframe (if datetime use 'datetime64[ns]')
    converters = None # For reading dataframe
    ignore_index = True # When concatting dataframes
    _reduce_reset_index = False
    _reduce_update_references = False
    
    def __init__(self, id={}, load=None, update=None, save=None, merge=None,*,
                 tickmgr={}, conns={}, name=None, reduce=1, TEST_MODE=False):
        isdict = isinstance(id, dict)
        iditer = iter(id)
        self.id = {}
        for attr in self.id_attrs:
            try: 
                value = id[attr] if isdict else next(iditer)
            except (KeyError, StopIteration):
                # Use class attribute if present
                clsv = getattr(self.__class__, attr, None)
                # inpsect.isfunction detects staticmethods and methods only
                # inspect.ismethod detects classmethods only
                if clsv is not None and not inspect.isfunction(clsv) and not inspect.ismethod(clsv):
                    value = getattr(self.__class__, attr)
                else:
                    raise ValueError('Got id: {}, which is missing some params from: {}'.format(id, self.id_attrs))
            self.id[attr] = value
        
        if self.set_id_attrs:
            for attr in self.id_attrs:
                setattr(self, attr, self.id[attr])
        
        self.id_str = '_'.join(str(x) for x in self.id.values())
        
        if name is None and getattr(self,'_name',None) is None:
            name = '{}_{}'.format(self.__class__.__name__, self.id_str)
        
        super().__init__(tickmgr=tickmgr, name=name)
        
        #if it is empty dataframe, then the default (empty) RangeIndex does not interfere with concatenating
        # (e.g. (empty) RangeIndex + DatetimeIndex -> DatetimeIndex)
        self.guts = init_data(self.template)
        
        if load is True: load = {}
        elif load is None or load is False: pass
        elif not isinstance(load,dict): load = {'tp': load}
        if isinstance(load,dict) and load.get('tp') is None:
            load = dict(load, tp=self.calc_load_tp)
            
        if reduce is True: reduce = {}
        elif reduce is None or reduce is False: pass
        elif not isinstance(reduce,dict): reduce = {'keep_periods': reduce}
        if isinstance(reduce,dict) and reduce.get('keep_periods') is None:
            reduce = dict(reduce, keep_periods=1)

        self._dnfo = {'load': load, 'merge': merge, 'reduce': reduce}
        self._ui = {
            'time_initiated': dt.utcnow(), 
            'time_started': None, 
            'time_loaded': None,
            'ts_last': {'save': None, 'update': None, 'merge': {}},
            'up_to_date_until': None,
            'merger_relay_created': None,
            'merger_relay_started': None,
            'merger_relay_closed': None,
        }
        
        _freq = self.save_freq[next(i for i,x in enumerate(self.save_freq) if x.isalpha()):]
        f_extra = {
            'save': {
                #'args': (self.calc_save_tp,),
                'kwargs': {'tp':self.calc_save_tp, 'reduce': True},
                'interval': self.save_freq,
                'sync': merging.SYNCS[_freq] if _freq in merging.SYNCS else 'random-0.4-0.8',
                'lock': 'next'},
        }
        
        for func_name,inp in zip(('update','save'),(update,save)):
            #NB! `no_set_event_on` defaults to lambda x: x is False;
            # can be overwritten it by passing None/another_function to the dict
            params = f_extra.get(func_name,{})
            temp = dict({
                'target': func_name,
                'lock_id': -1,
                'no_set_event_on': lambda x: x is False,
                'sync': 'first',
            }, **params)
            if isinstance(inp,bool): pass
            elif isinstance(inp,(int,float,td,str,pd.offsets.DateOffset) or hasattr(inp,'__call__')):
                temp['interval'] = inp
            elif isinstance(inp,dict):
                if inp.get('args'):
                    raise ValueError("Passing args to '{}' not allowed; got: {}".format(func_name,inp['args']))
                if 'kwargs' in inp:
                    inp = inp.copy()
                    inp['kwargs'] = dict(params.get('kwargs',{}), **(inp['kwargs'] if inp['kwargs'] is not None else {}))
                temp.update(inp)
                
            if inp not in (None,False):
                self.sched.update({func_name: temp})
    
        self.descr = self.describe()
        self.conns = conns
        self.TEST_MODE = TEST_MODE
        self._relay_create_merger()
        
    """@classmethod
    def from_id(cls,id,**kw):
        spec = inspect.getfullargspec(cls.__init__)
        return cls(**{x:y for x,y in id.items() if x in spec.args or x in spec.kwonlyargs},**kw)"""
        
    async def start(self):
        logger.debug("Starting routine '{}'".format(self.name))
        self._ui['time_started'] = dt.utcnow()
        if not self._ui['time_loaded'] and isinstance(self._dnfo['load'],dict):
            self.load(**self._dnfo['load'])
        self._relay_start_merger()
        await super().start()
        
    async def update(self):
        pass

    def load(self, tp, extend=False, **kw):
        tp = self._resolve_tp(tp)
        #elif tp is None: tp = self.calc_load_tp()
        tlogger.debug("{} - loading '{}'".format(tp,self.id_str))
        if kw.get('TEST_MODE') is None: kw['TEST_MODE'] = self.TEST_MODE
        self.guts = store.read_data(self.id, self.descr, tp, **kw)
        save_tp = DType.calc_save_tp(self)
        if save_tp:
            self._ui['ts_last']['save'] = save_tp[-1]
        self._ui['time_loaded'] = dt.utcnow()
        if extend: self.extend(tp)
    
    def save(self, tp, reduce=False, **kw):
        #tlogger0.debug('tp: {}'.format(tp))
        tp = self._resolve_tp(tp)
        #elif tp is None: tp = self.calc_save_tp()
        tlogger.debug('{} - saving {}'.format(tp,self.id_str))
        if not tp: return
        if kw.get('TEST_MODE') is None: kw['TEST_MODE'] = self.TEST_MODE
        store.save_data(self.guts, self.id, self.descr, tp, **kw)
        if tp: self._ui['ts_last']['save'] = tp[-1]
        if reduce: self.reduce()
        
    def merge(self, tp, **kw):
        tp = self._resolve_tp(tp)
        if kw.get('TEST_MODE') is None: kw['TEST_MODE'] = self.TEST_MODE
        store.merge_data(self.id, self.descr, tp, **kw)
        
    def _resolve_tp(self, tp):
        #if isinstance(tp,str): tp = getattr(self,tp)
        if hasattr(tp,'__call__') and not isinstance(tp,pd.DateOffset): tp = tp()
        return tp
         
    def _relay_create_merger(self):
        #if 'merge' not in self.sched: return
        merge = self._dnfo['merge']
        if not merge: return
        elif self.conns.get('merge') is None: return
        freqs = merge if isinstance(merge,(list,tuple)) else (
            [merge] if isinstance(merge,str) else store._get_higher_freqs(self.save_freq))
        if not freqs: return
        logger.debug('{} - relaying create merger.'.format(self.id_str))
        self.conns['merge'].send({
            'method': 'create',
            'data': {
                'id': self.id_str,
                'cls': self.merger_cls if self.merger_cls is not None else self.__class__,
                'args': (self.id,),
                'kwargs': {'TEST_MODE': self.TEST_MODE},
                'freqs': freqs,}
        })
        #del self.sched['merge']
        self._ui['merger_relay_created'] = dt.utcnow()
        
    def _relay_start_merger(self):
        if not self._ui['merger_relay_created']: return
        logger.debug('{} - relaying start merger.'.format(self.id_str))
        self.conns['merge'].send({
            'method': 'start',
            'data': self.id_str})
        self._ui['merger_relay_started'] = dt.utcnow()
        
    def _relay_stop_merger(self):
        if not self._ui['merger_relay_started']: return
        logger.debug('{}: relaying stop merger'.format(self.id_str))
        self.conns['merge'].send({
            'method': 'stop',
            'data': self.id_str})
        self._ui['merger_relay_closed'] = dt.utcnow()
        
    def calc_save_tp(self):
        ofs = freq_to_offset(self.save_freq)
        ts_last = self._ui['ts_last']['save']
        #utdu must be "closed", i.e. the actual last entry.
        # once it is given, it must be always updated, otherwise
        # it will null any new attempts to induce tp from self.guts
        utdu = self._ui['up_to_date_until']
        
        borders = du.get_fringe_entries(self.guts, key=self.time_key)
        if utdu:
            if not borders: borders = [utdu,utdu]
            else: borders[-1] = utdu
        tlogger.debug("'{}' fringes: {}".format(self.id_str,borders))
        r_borders = [dt_round(x,ofs) for x in borders]
        
        def calc_new_right():
            if not self.time_freq:
                return None
            ofs2 = freq_to_offset(self.time_freq)
            r2 = dt_round(borders[-1],ofs2)
            b2ra = r_borders[-1] + ofs
            b2rb = r2 + ofs2
            if b2ra == b2rb:
                return b2ra

        if r_borders:
            new_right = calc_new_right()
            if new_right:
                r_borders[-1] = new_right
                
            if ts_last is not None:
                #r_borders[0] = max(ts_last,r_borders[0])
                r_borders[0] = ts_last
            
            #if equal let them be, as it does no harm 
            # (and .load should init _ui['last_ts']['save'], we shouldn't return empty tuple)
            if r_borders[0] > r_borders[-1]:
                r_borders = []
                
        return tuple(r_borders)
            
    def calc_load_tp(self):
        """Override this method"""
        
    def calc_merge_tp(self, freq):
        ofs = freq_to_offset(freq)
        ts_last = self._ui['ts_last']['merge']
        f_last = ts_last.get(freq)
        r_now = dt_round(dt.utcnow(),ofs)
        if f_last is None: f_last = r_now - ofs
        return (f_last,r_now)
            
    def calc_reduce_tp(self):
        last_save = self._ui['ts_last']['save']
        if not last_save or not self._dnfo['reduce']: 
            return None
        keep = self._dnfo['reduce']['keep_periods']
        interval = self.get_ticker('save').interval
        keep_tp = (last_save-keep*interval, None)
        tlogger.debug("'{}' keep_tp: {}".format(self.id_str,keep_tp))
        return keep_tp
            
    def reduce(self):
        """Shortens itself on time dependent manner"""
        keep_tp = self.calc_reduce_tp()
        if keep_tp is None: return
        new_obj = du.slice_obj(self.guts,keep_tp,self.time_key)
        if self.ftype == 'csv' and self._reduce_reset_index:
            new_obj.reset_index(drop=True,inplace=True)
        self.guts = new_obj
    
    def extend(self):
        """Override this method"""
        
    def filter(self, params):
        pass
    
    def verify(self,**kw):
        return verify_data(self.guts, self.template, **kw)
    
    def init_from_template(self):
        self.guts = init_data(self.template)
        
    @classmethod
    def describe(cls):
        #index_dtype,converters,index_col
        d = {attr: getattr(cls,attr,None) for attr in 
             ['template','ftype','root','test_root','dir_fmt','file_fmt','time_key','init_data',
              'converters','index_col','index_dtype','ignore_index','encode','decode','ensure_integrity']}
        return d

    @classmethod
    def decode(cls, data):
        """Modifications may occur inplace. Called while loading."""
        return data
    
    @classmethod
    def encode(cls, data):
        """Modifications must NOT occur inplace. Called while saving."""
        return data
    
    @classmethod
    def ensure_integrity(cls, data):
        """Modifications must NOT occur inplace. Called after loading and before saving."""
        return data
    
    async def close(self):
        await super().close()
        self._relay_stop_merger()

  
class ShadowMerger(LogiProcess):
    def __init__(self, conn, cache_path=None, **kw):
        kw['name'] = create_name(kw.get('name'),self.__class__.__name__,_MERGER_NAMES)
        super().__init__(**kw)
        self.cache_path = cache_path
        self.conn = conn
        
    def run(self):
        logger.debug("Starting merger '{}'".format(self.name))
        merging.run(self.conn, self.cache_path)
    
    """def add_merger(self,cls,args,kwargs):
        self.conn.send()"""
        
