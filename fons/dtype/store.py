import os
import pandas as pd
import numpy as np
import json
import datetime
dt = datetime.datetime
td = datetime.timedelta

from fons.os import (delete_empty_dirs, make_dirpath)
from fons.io import DateTimeEncoder
import fons.log as _log
import fons.math.series as du
from fons.time import (dt_round, dt_isround, freq_to_offset, dt_strp)
from fons.verify import init_data


FREQS = ['MS','D','H','T']

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

#-----------------------------------------------------
    
DATE_FMT = '%Y-%m-%dT%H-%M-%S-%f'
OBS_DATE_FMT = '%Y-%m-%dT%H-%M-%S'

DIR_FMTS = {'MS': '%Y-%m',
            'D': '%d',
            'H': '%H'}
FILE_FMTS = {'MS': '%Y-%m',
             'D': '%Y-%m-%d',
             'H': '%Y-%m-%dT%H',
             'T': '%Y-%m-%dT%H-%M'}

PD_CONVERSIONS = {
    list: json.loads}


def _resolve_root(descr, TEST_MODE=None, root=None):
    if root is not None: return root
    return descr['root'] if not TEST_MODE else descr['test_root']


def _dissolve_tp(tp, max_freq='MS'):
    if tp is None: return []
    Ttp = [dt_round(x,'T') for x in tp]
    if Ttp[1] < tp[1]: Ttp = [Ttp[0], Ttp[1]+td(minutes=1)]
    
    Htp = [dt_round(x,'H') for x in tp]
    if Htp[0] < tp[0]: 
        Htp = [Htp[0]+td(hours=1), Htp[1]]
    
    Dtp = [dt_round(x,'D') for x in tp]
    if Dtp[0] < tp[0]: 
        Dtp = [Dtp[0]+td(1), Dtp[1]]
        
    Mtp = [dt_round(x,'MS') for x in tp]
    if Mtp[0] < tp[0]:
        Mtp = [Mtp[0]+pd.offsets.MonthBegin(), Mtp[1]]

    M = pd.date_range(Mtp[0],Mtp[1],freq='1MS', normalize=True)
    D = pd.date_range(Dtp[0],Dtp[1],freq='1D', normalize=True)
    H = pd.date_range(Htp[0],Htp[1],freq='1H')
    T = pd.date_range(Ttp[0],Ttp[1],freq='1T')
    
    if max_freq in ('M','MS',None):
        pass
    elif max_freq in ('D',):
        M = M[0:0]
    elif max_freq in ('H',):
        M = M[0:0]
        D = D[0:0]
    elif max_freq in ('T',):
        M = M[0:0]
        D = D[0:0]
        H = H[0:0]
    else:
        raise ValueError(max_freq)
        
    if M.shape[0]:
        D = D[(D < M[0]) | (D >= M[-1])]
        H = H[(H < M[0]) | (H >= M[-1])]
        T = T[(T < M[0]) | (T >= M[-1])]
        
    if D.shape[0]:
        H = H[(H < D[0]) | (H >= D[-1])]
        T = T[(T < D[0]) | (T >= D[-1])]
        
    if H.shape[0]:
        T = T[(T < H[0]) | (T >= H[-1])]
    
    dr = []
    
    offsets = [ pd.offsets.MonthBegin(),
                pd.offsets.Day(),
                pd.offsets.Hour(), 
                pd.offsets.Minute(), ]
    
    for x,ofs in zip((M,D,H,T),offsets):
        if x.shape[0] < 2:
            continue
               
        for y in x[:-1]:
            dr.append((y, y + ofs))

    return sorted(dr,key=lambda x: x[0])
    
    
def _get_higher_freqs(freq):
    _freq = freq[next((i for i,x in enumerate(freq) if x.isalpha()),0):]
    if _freq not in FREQS:
        raise ValueError('Unrecognized freq: {}'.format(freq))
    i = FREQS.index(_freq)
    return FREQS[:i]
            
            
def merge_data(id, descr, tp, freq='MS', include_longer_freqs=True, 
               delete_shorter_freqs=False, output_root=None,recycler=None, **kw):
    
    tlogger.debug('Merging tp:{} freq:{} id:{}'.format(tp,freq,id))
    
    try:
        freq_loc = FREQS.index(freq)
    except IndexError:
        raise ValueError("freq must one of the following: {}. Got '{}'".format(FREQS, freq))
    
    search_freqs = FREQS if include_longer_freqs else FREQS[freq_loc:]
    delete_freqs = FREQS[freq_loc+1:] if delete_shorter_freqs else []
    
    paths = get_paths(id, descr, tp, freqs=search_freqs, duplicates='include', **kw)
    #print('freqs:',search_freqs,'paths:,\n',paths,'kw:',kw)
    data = read_data(id, descr, tp, paths=paths, **kw)
    
    kw2 = kw.copy()
    if output_root is not None:
        kw2['root'] = output_root
    paths_saved = save_data(data, id, descr, tp, max_freq=freq, **kw2)
    
    #cleanup:
    any_removed = False
        
    for curfreq,subpaths in paths[delete_freqs].iteritems():
        for pth in subpaths.dropna():
            if pth in paths_saved: continue
            any_removed = True
            if recycler is not None:
                recycler(pth)
                continue
            try: os.remove(pth)
            except FileNotFoundError: pass
            except OSError as e:
                logger2.error('Can\'t delete {}'.format(pth))
                logger.exception(e)
                  
    if any_removed:
        trunk = get_trunk(id, descr, **kw) 
        delete_empty_dirs(trunk, recycler)
        
    if output_root is not None:
        trunk2 = get_trunk(id, descr, **kw2)
        delete_empty_dirs(trunk2, recycler)
        

def _delete_paths(paths, freqs=[], exclude=[],
                  delete_empty_dirs=[]):
    #cleanup:
    any_removed = False
        
    for curfreq,subpaths in paths[freqs].iteritems():
        for pth in subpaths.dropna():
            if pth in exclude: continue
            any_removed = True
            logger.info('_path_ removing: {}'.format(pth))
            try: os.remove(pth)
            except OSError as e:
                logger2.error('Can\'t delete {}'.format(pth))
                logger.exception(e)
             
    if any_removed:
        for trunk in delete_empty_dirs:
            delete_empty_dirs(trunk)
        

def _csv_params(descr):
    converters = descr['converters']
    temp = descr['template']
    conv_given = {} if converters is None else converters
    converters = temp.get('dtypes',{}).copy()
    converters.update(conv_given)
    
    parse_dates = [k for k,v in converters.items() if v == 'datetime64[ns]']
    converters = {k:v for k,v in converters.items() if v is str or k in conv_given} #doesn't work on csv for some reason (str->dtype:float)
    
    index_col = descr['index_col']
    index_dtype = descr['index_dtype']
    ic2 = index_col if isinstance(index_col, (list,tuple)) else [index_col]
    it2 = index_dtype if isinstance(index_col, (list,tuple)) else [index_dtype]
    #index_dtype in descr or temp?
    
    for dtype,col_nr in reversed(list(zip(it2,ic2))):
        if dtype == 'datetime64[ns]':
            parse_dates.insert(0,col_nr)

    #print('parse_dates:',parse_dates,'converters:',converters)
    d = {'index_col': index_col, 'parse_dates': parse_dates, 'converters': converters}#, 'sep': ',', 'decimal': '.'}
    
    return d
               

def read_data(id, descr, tp, **kw):
    json_load = (descr['ftype'] == 'json')
    if not json_load:
        tlogger.debug('getting csv_params')
        csv_params = _csv_params(descr)
    
    kw2 = {x:y for x,y in kw.items() if x not in ('paths',)}
    paths = get_paths(id,descr,tp,**kw2) if kw.get('paths') is None else kw['paths']
    dparts = []
    decode = descr['decode']
    init = descr['init_data']
    method = dparts.extend if json_load else dparts.append
    
    for ir in paths.iterrows():
        #tlogger.debug(ir)
        row = ir[1]
        path = row['path']
        logger.debug('_path_ loading: {}'.format(path))
        try:
            if json_load:
                with open(path,encoding='utf-8') as f:
                    dat = json.load(f)
                    if init: dat = init_data(dat)
            else:
                dat = pd.read_csv(path,**csv_params)
            if decode is not None:
                dat = decode(dat)
            method(dat)
        except Exception as e:
            logger.exception(e)
       
    if not len(dparts):
        #returns empty dataframe/list...
        return init_data(descr['template'])
    
    elif json_load:
        obj = du.slice_obj(dparts, tp, descr['time_key'])
    
    else:
        conc = pd.concat(dparts, ignore_index=descr['ignore_index'])
        #print(conc.dtypes)
        obj = du.slice_obj(conc, tp, descr['time_key'])

    ensure_integrity = descr['ensure_integrity']
    if ensure_integrity is not None:
        obj = ensure_integrity(obj)
        
    return obj


def save_data(obj, id, descr, tp,max_freq='MS', **kw):
    time_key = descr['time_key']
    tp = du.get_timestamps(tp)
    tp_slices = _dissolve_tp(tp, max_freq)
      
    paths_saved = []
    root = _resolve_root(descr,**kw)
    ftype = descr['ftype']
    encode = descr['encode']
    if ftype not in ('json','csv'):
        raise ValueError(ftype)
    lenf = lambda x: x.shape[0] if ftype == 'csv' else len(x)
    
    ensure_integrity = descr['ensure_integrity']
    if ensure_integrity is not None:
        obj = ensure_integrity(obj)
    
    for tp_slice in tp_slices:
        tlogger.debug('{} {}'.format(tp_slice, id))
        r = induce_datefmt(tp_slice)
        _dir = get_dir(id, descr, tp_slice, induce_datefmt_r=r, **kw)
        f_datefmt = r['file']
        
        fname = get_fname(id, descr, f_datefmt) + '.{}'.format(ftype)
        fpath = os.path.join(_dir, fname)
        obj2 = du.slice_obj(obj, tp_slice, time_key)
        
        if not lenf(obj2):
            logger.debug('{} is empty {}'.format(tp_slice, id))
            try: os.rmdir(_dir)
            except Exception: pass
            continue
        
        if encode is not None:
            obj2 = encode(obj2)
            
        paths_saved.append(fpath)
        logger.info('_path_ saving: {}'.format(fpath))
         
        if ftype == 'csv':
            index = descr['index_col'] is not None
            obj2.to_csv(fpath, index=index, encoding='utf-8')
            
        elif ftype == 'json':
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(obj2, f, ensure_ascii=False, cls=DateTimeEncoder)
        
    return paths_saved


def get_fname(id, descr, ts_tp_datestr, **kw):
    if isinstance(ts_tp_datestr, str):
        date_str = ts_tp_datestr
    elif isinstance(ts_tp_datestr, (list,tuple)):
        r = kw.get('induce_datefmt_r')
        date_str = induce_datefmt(ts_tp_datestr) if not r else r['file_fmt']
    elif isinstance(ts_tp_datestr, dt):
        date_fmt = DATE_FMT #if d_type != 'obs' else OBS_DATE_FMT
        date_str = du.format_ts(ts_tp_datestr, date_fmt)
    else:raise TypeError(ts_tp_datestr)
    
    return "_".join([date_str] + [id.get(x) for x in descr['file_fmt']])


def get_dir(id, descr, tp, **kw):    
    kw2 = {x:y for x,y in kw.items() if x not in ('induce_datefmt_r',)}
    dir1 = get_trunk(id, descr, **kw2)
    
    if not kw.get('induce_datefmt_r'):
        r = induce_datefmt(tp)
    else: r = kw['induce_datefmt_r']
    
    date_parts = r['dir']
    
    if r['period'] == 'month':
        return make_dirpath(dir1)
    elif r['period'] != 'other':
        return make_dirpath(dir1, *date_parts)
    else: return make_dirpath(dir1, 'custom_fmt')
    

def induce_datefmt(tp):
    if any(not isinstance(x, dt) for x in tp):
        raise ValueError(tp,'contains non datetime element')
        
    len_tp = tp[1] - tp[0]
    
    if td(28) <= len_tp <= td(31) and dt_isround(tp[0],'month') and tp[1].month != tp[0].month:
        return {'period': 'month', 
                'dir': None, 
                'file': tp[0].strftime(FILE_FMTS['MS'])}
    
    elif len_tp == td(1) and dt_isround(tp[0],'day'):
        return {'period': 'day', 
                'dir': (tp[0].strftime(DIR_FMTS['MS']),), 
                'file': tp[0].strftime(FILE_FMTS['D'])}
    
    elif len_tp == td(hours=1) and  dt_isround(tp[0],'hour'):
        return {'period': 'hour', 
                'dir': (tp[0].strftime(DIR_FMTS['MS']),tp[0].strftime(DIR_FMTS['D'])), 
                'file': tp[0].strftime(FILE_FMTS['H'])}
    
    elif len_tp == td(minutes=1) and  dt_isround(tp[0],'minute'):
        return {'period': 'minute', 
                'dir': (tp[0].strftime(DIR_FMTS['MS']),tp[0].strftime(DIR_FMTS['D']),tp[0].strftime(DIR_FMTS['H'])), 
                'file': tp[0].strftime(FILE_FMTS['T'])}
    
    else: return {'period': 'other', 
                  'dir': None, 
                  'file': du.format_tp(tp, DATE_FMT)}
    
#-------------------------------------------------------------------------------------------


def get_trunk(id, descr, assert_existence=False, **kw):
    root = _resolve_root(descr, **kw)
    order = descr['dir_fmt']
    parts = [root] + [id.get(x) for x in order]
    trunk = os.path.join(*parts)
    exists = os.path.exists(trunk)
    if not exists:
        if assert_existence:
            raise OSError('Path {} does not exist'.format(trunk))
        make_dirpath(*parts)
    
    return trunk

              
def get_paths(id, descr, tp, min_periods=None, duplicates='drop', freqs=FREQS, **kw):
    tp = du.get_timestamps(tp)
    if any(x not in FREQS for x in freqs):
        raise ValueError('`freqs` contains not allowed items; got: {}'.format(freqs))
    elif any(freqs.count(x) > 1 for x in freqs):
        raise ValueError('`freqs` contains duplicates; got: {}'.format(freqs))   
    freqs =  [x for x in FREQS if x in freqs]

    basedir = get_trunk(id, descr, assert_existence=False, **kw) #assert_existence=True,
    
    mb = pd.offsets.MonthBegin()
    start_m, end_m = [dt_round(x,mb) for x in tp]
    if tp[1] == end_m:
        end_m -= mb
    
    element = freq_to_offset(FREQS[-1])
    start_t, end_t = [dt_round(x, element) for x in tp]
    if tp[1] == end_t:
        end_t -= element
    element_arr = pd.date_range(start_t, end_t, freq=element)

    drop_duplicates = (duplicates == 'drop')
    ext = '.'+descr['ftype']
    
    freq_parts = {f: [] for f in FREQS}
    FREQS2 = ['YS'] + FREQS
    
    def _map_freq(f):
        return {'M': 'MS', 'Y': 'YS'}.get(f, f)
    
    def unit(r,start,dir):
        try: 
            freq = FREQS2[r]
            next_freq = FREQS2[r+1]
            files = os.listdir(dir)
        except (IndexError,OSError):
            return
        
        ofs = freq_to_offset(_map_freq(freq))
        next_ofs = freq_to_offset(_map_freq(next_freq))
        
        end = dt_round(tp[1],ofs)+ofs if not r else start+ofs
        units = pd.date_range(start, end, freq=next_ofs, closed='left')
        if not r: units = units[(units >= start_m) & (units <= end_m)]
        units_str = units.strftime(DIR_FMTS[next_freq]) if next_freq in DIR_FMTS else [None]*units.shape[0]
        units_str_full = units.strftime(FILE_FMTS[next_freq])
        pnf = freq_parts[next_freq]
        
        for ts, ts_str, ts_str_full in zip(units, units_str, units_str_full):
            fn = get_fname(id, descr, ts_str_full) + ext
            unit_fpth = os.path.join(dir, fn)
            
            if next_freq in freqs and fn in files:
                unit_fpth = os.path.join(dir, fn)
                ts_arr = pd.date_range(ts, ts+next_ofs, freq=element_arr.freq, closed='left')
                ts_arr = ts_arr[(ts_arr>=start_t) & (ts_arr <= end_t)]

                if ts_arr.shape[0]:
                    pnf.append(pd.Series(unit_fpth, index=ts_arr))
                    if drop_duplicates:
                        continue
            
            if not ts_str: continue
            unit(r+1, ts, os.path.join(dir, ts_str))
        
    unit (0, dt_round(tp[0],'1YS'), basedir)
    
    for f,x in freq_parts.items():
        if not len(x): continue
        if x[0].index[0] > start_t:
            x.insert(0,pd.Series(np.nan, index=[start_t]))
        if x[-1].index[-1] < end_t:
            x.append(pd.Series(np.nan, index=[end_t]))

    freqs_concatted = {f: pd.concat(x) for f,x in freq_parts.items() if x}
    freqs_resampled = {f: x.resample(element).asfreq() for f,x in freqs_concatted.items()}

    paths = pd.DataFrame(freqs_resampled, index=element_arr).dropna(how='all')
    paths = paths.reindex(columns=[x for x in FREQS if x in paths.columns])
    paths['path'] = paths.fillna(method='ffill',axis=1)[paths.columns[-1]] if paths.columns.shape[0] else np.nan
    paths = paths.reindex(columns=['path']+FREQS)#.dropna(subset=['path'])
    
    if min_periods and paths.shape[0] / element_arr.shape[0] < min_periods:
        raise ValueError('< min periods `{}`'.format(min_periods))
        
    paths = paths.drop_duplicates(subset=['path'])
    
    return paths



if __name__ == '__main__':
    print(_dissolve_tp((dt(2018, 10, 26, 3, 7,1), dt(2018, 10, 26, 3, 8,5)),'MS'))
    print(_dissolve_tp((dt(2018, 9, 29, 23, 58, 2), dt(2018, 11, 2, 1, 0, 1)),'MS'))
    #print(_dissolve_tp((dt(2018, 10, 1), dt(2018, 11, 1)),'H'))
