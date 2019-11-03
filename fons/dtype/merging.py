import sys,os
import asyncio
import threading
import functools
import json
import datetime
dt = datetime.datetime
td = datetime.timedelta

from fons.aio import call_via_loop_afut
from fons.io import SafeFileLock, wait_filelock
import fons.log as _log
from fons.host import Server, ServerError
from fons.sched import AsyncTicker
import fons.time as fontime

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

SYNCS = {
    'MS': 'random-0.001861..0.00744', #1T(01:15)-05 on 28-day months
    'D': 'random-0.0327..0.038', #yT00:(47-55)
    'H': 'random-0.525..0.716', #yTx:((31:30)-43)
    'T': 'random-0.52..0.8', #for store.save only, merge takes no "T" freq
}

METHOD_PARAMS = {
    'start': ['cls','args','kwargs','freqs'],
    'stop': ['name'],}

_FREQS = ['H','D','MS']
_ID_MULTI = {'_multi_': [{'_type_': str},{'_type_':int}]}
_INPUT_METHOD_CREATE = {
    '_type_': dict,
    'dtypes': {
        'method': {'_value_': 'create'},
        'data': {
            '_type_': dict,
            'dtypes': {
                'id': _ID_MULTI,
                'cls': {'_type_': type},
                'args': {'_defval_':None, '_multi_': [{'_type_':list},{'_type_':tuple}]},
                'kwargs': {'_defval_':None, '_type_': dict},
                'freqs': {'_type_': list, 'unit': {'_multi_': [{'_value_': x} for x in _FREQS]}},
            },'keys_optional': ['args','kwargs'],},
}}
_INPUT_METHOD_START = {
    '_type_': dict,
    'dtypes':{
        'method': {'_value_': 'start'},
        'data': _ID_MULTI},
        #"""{'_type_': list, 'unit': {'_multi_': [{'_type_': str},{'_type_':int}]}},"""
}
_INPUT_METHOD_STOP = {
    '_type_': dict,
    'dtypes': {
        'method': {'_value_': 'stop'},
        'data': _ID_MULTI}
}
INPUT = {
    '_multi_': [_INPUT_METHOD_CREATE, _INPUT_METHOD_START, _INPUT_METHOD_STOP]}

mergers = {}
to_recycle = []
_recycle_lock = threading.Lock()
_terminated = asyncio.Event()


def create_merger(cls, args, kwargs):
    if args is None: args = tuple()
    if kwargs is None: kwargs = {}
    #dtype = cls.from_id(*args,**kwargs)
    dtype = cls(*args,**kwargs)
    return dtype


def create_merger_sched(merger, freqs):
    wrap_tp = lambda freq: functools.partial(merger.calc_merge_tp,freq)
    calc_sync = lambda freq: SYNCS[freq] 
    merger.sched = {
        'merge_{}'.format(freq): {
            'target': 'merge', 
            'args': (wrap_tp(freq),),
            'kwargs': {
                #'include_longer_freqs': False,
                'delete_shorter_freqs': True,
                'recycler': add_to_recycle},
            'lock_id': -1,
            'interval': freq,
            'sync': calc_sync(freq),
            'lock': 'next',} 
        for freq in freqs}
    merger.create_schedule()


def handle_input(inp):
    loop = asyncio.get_event_loop()
    data = inp['data']
    if inp['method'] == 'create':
        id = data['id']
        if id in mergers:
            raise ServerError("Merger with id '{}' already exists".format(id))
        logger2.info("Creating merger with id '{}'".format(id))
        merger = create_merger(data['cls'],data.get('args'),data.get('kwargs'))
        merger.name += '[merger]'
        merger._tickmgr.name = merger.name + '-TickManager'
        create_merger_sched(merger,data['freqs'])
        mergers[id] = merger
    elif inp['method'] in ('start','stop'):
        id = data
        if id not in mergers:
            raise ServerError("Merger with id '{}' does not exist".format(id))
        merger = mergers[id]
        corofunc = merger.start if inp['method'] == 'start' else merger.close
        action = 'Starting' if inp['method'] == 'start' else 'Closing'
        logger.info("{} merger with id '{}'".format(action,id))
        call_via_loop_afut(corofunc)
        #tlogger.debug('Loop is running: {}'.format(loop.is_running()))
        if inp['method'] == 'close': del mergers[id]


def add_to_recycle(path, expiry=180):
    if not isinstance(expiry,dt):
        expiry = dt.utcnow() + fontime.freq_to_offset(expiry)
    with _recycle_lock:
        to_recycle.append((expiry,path))


async def delete_expired(fpath=None, force=False):
    now = dt.utcnow()
    with _recycle_lock:
        ln = len(to_recycle)
        for i,item in enumerate(reversed(to_recycle)):
            expiry,path = item
            if now > expiry or force:
                try:
                    if os.path.isdir(path):
                        os.rmdir(path)
                    else:os.remove(path)
                except FileNotFoundError: pass
                except OSError as e:
                    logger.exception(e)
                finally: to_recycle.pop(ln-(i+1))
    if fpath:
        _save_expiry(fpath)


def _read_expiry(fpath):
    wait_filelock(fpath)
    try:
        with open(fpath,encoding='utf-8') as f:
            return [(fontime.pydt(x[0]),x[1]) for x in json.load(f)]
    except OSError:
        return []
    
    
def _save_expiry(fpath):
    with _recycle_lock:
        to_save = [[int(fontime.timestamp(x[0])),x[1]] for x in to_recycle]
    with SafeFileLock(fpath,2):
        with open(fpath,'w',encoding='utf-8') as f:
            json.dump(to_save,f)

    
def run(conn, fpath=None):#sys.argv):
    global to_recycle
    loop = asyncio.get_event_loop()
    
    """try: fpath = argv[0]
    except IndexError: fpath = None"""
    
    if fpath:
        logger.debug("Recycling data is read/stored from file {}".format(fpath))
        try: to_recycle = _read_expiry(fpath)
        except Exception as e:
            logger2.error(e)
            logger.exception(e)
    else:
        logger2.warning("No recycling path given. All non-expired files will be deleted upon termination.")
    
    recycling = AsyncTicker(delete_expired,'1T',args=(fpath,),name='ReCycler')
    
    def terminate():
        for m in list(mergers.values()) + [recycling]:
            call_via_loop_afut(m.close)
        _terminated.set()
    
    if conn is not None:
        server = Server(conn,handle_input,on_exit=terminate,exit_cmd=lambda x: x is None,verify=INPUT,
                        name='DTypeMerger[Server]',loop=loop)
        server.start()
    
    loop.run_until_complete(asyncio.wait([recycling.loop()])) #_terminated.wait()
    if fpath:
        _save_expiry(fpath)
    else:
        logger2.info("Deleting all non-expired files.")
        delete_expired(force=True)
    logger2.info("`merging` terminated")
        
"""if __name__ == '__main__':
    main()"""
