from collections import OrderedDict as OD
import pandas as pd
import numpy as np
import datetime as dt
from dateutil.parser import parse as parsedate
import traceback
import warnings

from fons.errors import BadInstruction
from fons.pyops import (compare, copy as _copy)

mappings  =  [[['pd.DataFrame','pandas.DataFrame','pandas.core.frame.DataFrame'],pd.DataFrame],
              [['pd.Series','pandas.Series','pandas.core.series.Series'],pd.Series],
              [['list'],list],
              [['tuple'],tuple],
              [['dict','dictionary'],dict],
              [['OrderedDict'],OD],
              [['set'],set],
              [['string','str'],str],
              [['int','int8','int16','int32','int64','integer'],int],
              [['float','float16','float32','float64'],float],
              [['np.ndarray','numpy.ndarray'],np.array],
              [['dt.date','datetime.date','date'],dt.date],
              [['dt','dt.datetime','datetime.datetime','datetime','datetime64[ns]'],dt.datetime],
              [['td','dt.timedelta','datetime.timedelta','timedelta','timedelta64[ns]'],dt.timedelta],
              [['object'],str],
              [['type'],type],]

           
MAPPING = {}
for strnames,func in mappings:
    MAPPING.update(dict.fromkeys(strnames, func))
    MAPPING.update({func: func})
    
EQUALS = {np.datetime64: pd.Timestamp,
          dt.datetime: pd.Timestamp,
          np.timedelta64: pd.Timedelta,
          dt.timedelta: pd.Timedelta,
          float: int}

PD_EQUALS = {np.datetime64: pd.Timestamp,
             dt.datetime: pd.Timestamp,
             np.timedelta64: pd.Timedelta,
             dt.timedelta: pd.Timedelta,
             int: float}
  
PD_SPECIAL = {dt.datetime: 'datetime64[ns]',
              np.datetime64: 'datetime64[ns]',
              pd.Timestamp: 'datetime64[ns]',
              dt.timedelta: 'timedelta64[ns]',
              np.timedelta64: 'timedelta64[ns]',
              pd.Timedelta: 'timedelta64[ns]',}


TYPES = ('type','function','module')
_TYPES = tuple([cls for cls in object.__subclasses__() if cls.__name__ in TYPES])
    

HANDLEABLES = (list, tuple, set)
IMMUTABLES = (int, float, str, bool, tuple, type(None))
CONTAINERS = (dict, list, tuple, set, pd.Series, pd.DataFrame, pd.Index, np.ndarray)
COPY_METHOD = (pd.DataFrame, pd.Series, pd.DatetimeIndex, pd.Index, np.ndarray)


RESERVED = ('_type_', '_call_', '_value_', '_defval_', '_copy_', '_isnorm_', '_multi_')
NORM_EXTRA = {'_defval_': {'_type_':str,
                           '_value_': '_keep_'}}

    
def _map(item, *default, **kw):
    if not isinstance(item, str):
        return item
    
    obj = None
    
    if item in MAPPING:
        obj = MAPPING[item]
    elif __name__ == '__main__':
        obj = getattr(__builtins__, item, None)
    else:
        obj = __builtins__.get(item, None)
    
    if obj is None or type(obj).__name__ not in TYPES:
        if not len(default):
            raise BadInstruction('Item {} not known.'.format(item))
        else:
            return default[0]
        
    if kw.get('pd_dtype'):
        try: obj = PD_SPECIAL.get(obj,obj)
        except TypeError: pass
    
    return obj
    
def _isinstructions(x):
    if not isinstance(x, dict):
        return False
    elif not any(k in RESERVED for k in x.keys()):
        return False
    
    return True 

def _isnorm(x):
    if not isinstance(x, dict):
        return False
    elif not x.get('_isnorm_'):
        return False
    
    return True
#----------------------------------------

def normalise(data):
    init_data(data)
    normalised = normalise_element(data)
    
    return normalised


def fill(x, norm, **kw):
    return verify_data(x,norm,mode='fill',**kw)

#----------------------------------------

def init_data(x):
    obj = None
    _type = type(x)
    _name = _type.__name__
    
    if _type is dict:
        obj = init_from_dict(x)
    
    elif _type not in HANDLEABLES:
        obj = _copy(x)

    
    else:
        alist = [init_data(v) for v in x]
            
        try:
            call = _map(_name)
            obj = call(alist)
                
        except ValueError:
            obj = alist
            
        except Exception:
            traceback.print_exc()
            obj = alist
        
    return obj



def init_from_dict(D):
    add_to = {}
    if _isinstructions(D):
        return init_instructions(D)
    
    #initiating its values (plus making copy of the dict)
    for n,v in D.items():
        obj = init_data(v)
        add_to[n] = obj
              
    return add_to 
        
        
        
def init_instructions(D):
    normalise_element(D)
    
    if '_copy_' in D:
        return _copy(D['_copy_'])
    
    _type_ = D.get('_type_')
    constructor = _map(_type_,None)
    
    if '_defval_' in D:
        return init_data(D['_defval_'])
    
    elif D.get('_call_','-') in (False,None):
        return None
    
    elif '_multi_' in D:
        return init_data(D['_multi_'][0])
    
    elif _type_ in TYPES or constructor in _TYPES:
        return _map(D.get('_value_'))
    
    #_value_ is used as an alternative to _call_() and _type_() 
    elif '_value_' in D:
        return init_data(D['_value_'])
    


    args,kw = [],{}
    
    if isinstance(D.get('_args'),(list,tuple)):
        args = init_data(D['_args'])
    
    if isinstance(D.get('_kw'),dict):
        kw = init_data(D['_kw'])
    

    if not len(args) or not len(kw):
        args2,kw2,call2 = _known_types(constructor,D)
        if not len(args):
            args = args2
        kw2.update(kw)
        kw = kw2
    
    
    if '_call_' not in D:
        call = call2
    else:call = _map(D['_call_'])
            
    #print(_type.__name__,'args:',args,'kw:',kw)
    obj = call(*args,**kw)
    D['_copy_'] = _copy(obj)
    
    return obj



def _known_types(constructor, D):
    
    #vname = vtype.__name__
    args = []
    kw = {}
    call = constructor


    if constructor in (pd.Series, pd.DataFrame):
        data = init_data(D.get('data'))
        index = init_data(D.get('index'))
        dtype = MAPPING.get(D.get('dtype'))
        
        name = init_data(D.get('name'))
        columns = init_data(D.get('columns'))
        dtypes = D.get('dtypes')
            
        if constructor is pd.DataFrame:
            if dtypes:
                if not isinstance(dtypes,dict):
                    dtypes = OD(init_data(dtypes))
                    D['dtypes'] = dtypes
                    """if not D.get('_dtypes'):
                    D['_dtypes'] = OD(k:{'_type_': type(v)} for k,v in dtypes.items())"""
                    
                if not isinstance(data,dict):
                    data = OD([[c,pd.Series(data, index=index, dtype=_map(d,None,pd_dtype=True))] for c,d in D['dtypes'].items()])
                else:
                    data = OD([[c,pd.Series(data.get(c), index=index, dtype=_map(d,None,pd_dtype=True))] for c,d in D['dtypes'].items()])
            
            if not columns:
                D['columns'] = list(dtypes.keys())
                
            kw.update({'data':data,'index':index,'columns':columns,'dtype':dtype})
            
        else:
            kw.update({'data':data,'index':index,'name':name,'dtype':dtype})
            
            
    elif constructor is dict:
        new_d = {}
        items = []

        if D.get('items'):
            items = D['items']
            if isinstance(items,dict):
                items = list(items.items())
            
        elif D.get('keys'):
            keys = D['keys']
            if 'values' in D:
                values = D['values']
            elif 'value' in D or 'v' in D:
                values = [D.get('value',D.get('v'))] * len(keys)
            else:
                values = [D.get('unit')] * len(keys)
            
            items = list(zip(keys,values))
            
        elif D.get('dtypes'):
            #only "overwrites" non-instructions:
            default_dtype = D.get('default_dtype',None)
            dtypes = D['dtypes']
            if not isinstance(dtypes,dict):
                dtypes = OD(dtypes)
            for k,v in dtypes.items():
                if not _isinstructions(v):
                    d = {'_type_': _map(v)}
                    normalise_element(d, default=default_dtype)
                else:
                    d = v#normalise_element(v) #don't use default=v, inf recursion
                
                items.append([k,d])
                
            
        new_d = init_data(items)
        args.append(new_d)
        
        #This won't be executed every time, as _known_types is not called if _copy_ exists
        if True:
            D['keys'] = [itm[0] for itm in new_d]
            #For being able to verify_data later (itm[1] -> {'_type_':type(itm[1]),_value_: itm[1])}
            items = [[itm[0],normalise_element(itm[1])] for itm in items]
            D['items'] = items #the instr dicts in items have been normalised due to init_data(items)
            init_data(D.get('unit'))
            

        
    elif constructor is dt.datetime:
        value = D.get('value', D.get('v'))
        
        if isinstance(value,str):
            args.append(value)
            
            if D.get('format'):
                call = dt.datetime.strptime
                args.append(D['format'])
            else:
                call = parsedate 
            
        elif isinstance(value, dt.datetime):
            args.extend([value.year, value.month, value.day, value.hour,
                         value.minute, value.second, value.microsecond])
        
        elif isinstance(value,(list,tuple)):
            args.extend(value)
            
        elif isinstance(value,(int,float)):
            call = dt.datetime.utcfromtimestamp
            args.append(value/1000)
            
        else:
            raise BadInstruction(constructor, D, value)
            
    
    elif constructor is dt.timedelta:
        value = D.get('value',D.get('v'))
        
        if isinstance(value,(list,tuple)):
            args.extend(value)
            
        elif isinstance(value,(int,float)):
            #microseconds
            args.extend([0,0,value*1000])
            
        else:
            raise BadInstruction(constructor, D, value)  
            
            
    elif constructor in (list,tuple,set):
        value = D.get('value', D.get('values', D.get('v')))
        if value: args.append(init_data(value))
        
        if D.get('unit'):
            init_data(D['unit'])
            
            
    elif constructor in (str,int,float):
        v = D.get('value', D.get('v'))
        if v: args.append(init_data(D['value']))
            
    else:
        args.append(init_data(constructor))
            
    #print('args_now:',args)    
            
    return args, kw, call



#--------------------------------------------

def normalise_element(x, default='_nan_'):
    if _isnorm(x): return x

    if _isinstructions(x):        
        d = x
        if '_defval_' in d:
            d['_defval_'] = normalise_element(d['_defval_'])
        
        if _isinstructions(d.get('_value_')):
            d['_value_'] = init_data(d['_value_'])
            
        if '_type_' in d:
            d['_type_'] = _map(d['_type_'])
            if not isinstance(d['_type_'],type):
                raise BadInstruction("'_type_' kw's value must inherit from <class 'type'>",d)
            if d['_type_'] in TYPES + _TYPES:
                d['_value_'] = _map(d.get('_value_'))
        elif '_value_' in d:
            d['_type_'] = type(d['_value_'])
        elif '_multi_' in d: pass
        elif '_defval_' in d:
            d['_type_'] = type(init_data(d['_defval_']))
        else:
            raise BadInstruction('Missing "_type_" keyword: {}'.format(x.keys()))
        
        #normalise the "dtypes"/"items"/..and_other keywords
        if '_type_' in d and d['_type_'] not in (dt.datetime, dt.timedelta):
            _known_types(d['_type_'], d)
            
        size = d.get('size')
        if size is None: pass
        elif not isinstance(size,(int,float,dict)):
            raise BadInstruction('"size" must be int/float/dict; got: {}'.format(type(size)))
        elif isinstance(size,(int,float)):
            d['size'] = {'exact': size}
        else:
            for arg in ('min','max','exact'):
                value = size.get(arg)
                if value is None: continue
                elif not isinstance(value,(int,float)):
                    raise BadInstruction('"size" keyword "{}" must be of type int/float; got: {}'.format(
                        arg,type(value)))
             
    else:
        d = {'_type_': type(x),
             '_value_': x}
    
    
    if not isinstance(default,str) or default != '_nan_':
        d['_defval_'] = normalise_element(default)
        
    #normalise the "_multi_" keyword items
    for i,item in enumerate(d.get('_multi_',[])):
        if not _isnorm(item):
            init_data(item)
            #d['_multi_'][i] = normalise_element(item)
        
        
    d['_isnorm_'] = True
                
    
    return d

#-------------------------------------

def verify_data(x, norm, mode='verify', **kw):
    if not _isnorm(norm): norm = normalise(norm)
    if mode not in ('verify','fill'):
        raise ValueError('Wrong mode: {}'.format(mode))
    handler = {k: kw.get(k,'error') for k in ('missing','extra','type')}
    if mode == 'fill': handler['missing'] = 'ignore'
    
    x_verified = x
    _type = type(x)
    _tname = _type.__name__
    
    trace = kw.get('trace',[])
    trace2 = trace + ['({}){}'.format(len(trace), _tname)]
    
    has_default = '_defval_' in norm
    _default = norm.get('_defval_')
    has_value = '_value_' in norm
    _value_ = norm.get('_value_')
    
    correct_types = ()
    correct_types2 = ()
    
    t_ok = v_ok = False
    passed = lambda: t_ok and v_ok
        
        
    if 'norm_extra' in kw:
        try: 
            if _isinstructions(kw['norm_extra']):
                verify_data(x, kw['norm_extra'], mode, **handler)
            else:
                verify_data(x,normalise_element({}, default=kw['norm_extra']), mode, **handler)
        except Exception: pass
        else: t_ok = v_ok = True
        
        
    if not passed() and has_default:
        _type1 = _map(_default['_type_'])   
        _type1a = EQUALS.get(_type1)
        
        correct_types = tuple(filter(lambda k:k, set([_type1, _type1a])))
        
        if _type in correct_types and compare(x, init_data(_default)):
            t_ok = v_ok = True
        

    if not passed() and '_multi_' in norm:
        exceptions = []
        for i,n in enumerate(norm['_multi_']):
            try:
                verify_data(x, n, 'verify', trace=trace, **handler)
                t_ok = v_ok = True
                if mode == 'verify': break
                x_verified = verify_data(x, n, mode, trace=trace, **handler)
            except Exception as e:
                exceptions.append((i,e))
            else: break
            
        if not passed():
            raise Exception('_multi_ errors: {}'.format(exceptions))
        else:
            return x_verified
        
    
    if not passed():
        _type2 = _map(norm['_type_'])

        try:
            _type2a = EQUALS.get(_type2)
        except TypeError as e:
            raise BadInstruction(trace2, type(norm['_type_']), x, norm)

        correct_types2 = tuple(filter(lambda k:k, set([_type2, _type2a])))
        
        if _type in correct_types2:
            t_ok = True
        
        if not has_value:
            v_ok = True
        elif t_ok and compare(x, _value_):
            v_ok = True
                
       
    if not passed():
        if not t_ok:
            got = _tname #'<{}>'.format(_name)
            #correct = '<{}>'.format(">,<".join([t.__name__ for t in correct_types]))
            correct = ",".join([t.__name__ for t in correct_types2])
            e_type = TypeError  
        else:
            got = x
            correct = _value_
            e_type = ValueError
            
        if handler['type'] == 'error':
            #print(_type, correct_types, correct_types2, x, _value_, type(_value_))
            raise e_type('{}; Got:{}, Expected:{}'.format("".join(trace2), got, correct))
        elif handler['type'] == 'warn':
            warnings.warn('{}; Got:{}, Expected:{}'.format("".join(trace2), got, correct))
    
    
    try: iter(x)
    except TypeError: pass
    else: x_verified = _verify_elements(x, norm, mode, trace2, handler)
    
    """if isinstance(x,CONTAINERS):
        x_verified = _verify_elements(x, norm, mode, trace=trace2, handler)"""
        
    return x_verified
    
    
def _verify_elements(x, norm, mode, trace, handler):

    is_unit = 'unit' in norm
    unit = norm.get('unit')
    
    if is_unit and not _isinstructions(unit):
        norm['unit'] = normalise_element(unit)
        unit = norm['unit']
    elif is_unit: normalise_element(unit)
    
    x_verified = x
       
    if isinstance(x,dict):
        nitems = norm.get('items')
        
        if nitems:
            nkeys = [itm[0] for itm in nitems]
            missing = _verify_keys(x.keys(),nkeys,trace,handler)
            
            if mode == 'fill':
                #messes up order if OD
                n_inited = init_data(norm)
                #if len(missing): print(trace,'missing:',missing)
                x.update({k:v for k,v in n_inited.items() if k in missing})
                
            for nk,nv in nitems:
                if nk in missing:continue
                trace2 = trace[:-1] + [''.join(trace[-1:]) + '({})(key){}'.format(len(trace),nk)]
                xv = verify_data(x[nk], nv, mode, trace=trace2, **handler)
                #if mode == 'fill': x[nk] = xv  #this would overwrite! we just want to fill missing, as above

           
        if is_unit:
            for k,v in x.items():
                trace2 = trace[:-1] + [''.join(trace[-1:]) + '({})(key){}'.format(len(trace),k)]
                xv = verify_data(v, unit, mode, trace=trace2, **handler)
                #if mode == 'fill': x[k] = xv
        
    
    elif isinstance(x,(pd.Series,pd.DataFrame)):
        ndtype0 = norm.get('dtype')
        
        ncols = norm.get('columns')
        nindex = norm.get('index')
        
        ndtypes = norm.get('dtypes')
        dtypes = x.dtypes
        missing_ind,missing_cols = [],[]
        
        if isinstance(x,pd.DataFrame):
            missing_cols = _verify_keys(x.columns,ncols,trace,handler)
            
        if nindex: missing_ind = _verify_keys(x.index,nindex,trace,handler)
        
        if mode == 'fill' and len(missing_ind) or len(missing_cols):
            x_new = init_data(norm)
            if isinstance(x,pd.Series): x_new.loc[x.index] = x
            else: x_new.loc[x.index,x.columns] = x
            x_verified = x_new
            
        wrong_dtypes = []
        dtypes = x.dtypes.iteritems() if isinstance(x,pd.DataFrame) else [(x.name,x.dtype)]
        
        for c,itm in dtypes:
            dtype = _map(itm.name,pd_dtype=True)
            ndtype = _map(ndtype0,pd_dtype=True) if ndtype0 else _map(ndtypes[c],pd_dtype=True)
            
            #both may be strings (datetime64[ns])
            #however. int may be
            if dtype != ndtype and dtype is not PD_EQUALS.get(ndtype):
                wrong_dtypes.append({c:(dtype,ndtype)})
                
                
            if len(wrong_dtypes):
                trace2 = ''.join(trace) +'({})'.format(len(trace))
                if handler['type'] == 'error':
                    raise TypeError('Trace {}; Wrong dtypes: ({})'.format(trace2,wrong_dtypes))
                elif handler['type'] == 'warn':
                    warnings.warn('Trace {}; Wrong dtypes: ({})'.format(trace2,wrong_dtypes))
            
            
    else: #if isinstance(x,(list,tuple,set)) or is_iterable:
        norm_extra = {}
        if not is_unit:
            nvalues = norm.get('value',norm.get('values',norm.get('v',[])))
            new = [verify_data(v,nv,mode,trace=trace,norm_extra=NORM_EXTRA,**handler) for v,nv in zip(x,nvalues)]
        else:new = [verify_data(v,unit,mode,trace=trace,norm_extra=NORM_EXTRA,**handler) for v in x]
        
        size = norm.get('size')
        if size is not None:
            len_x = len(x)
            for arg,op in [('min',lambda y: len_x>=y),
                           ('max',lambda y:len_x<y),
                           ('exact',lambda y: len_x==y)]:
                y = size.get(arg)
                if y is None: continue
                satisfied = op(y)
                if satisfied: continue
                
                trace2 = ''.join(trace)
                if handler['type'] == 'error':
                    raise ValueError('{}; Wrong size: {}, {}: {}'.format(trace2,len_x,arg,y))
                elif handler['type'] == 'warn':
                    warnings.warn('{}; Wrong size: {}, {}: {}'.format(trace2,len_x,arg,y))

        if mode == 'fill':
            norm_new = _copy(norm)
            norm_new.update({'_copy_':None,'value':new,'_value_':None})
            x_verified = init_data(norm_new)
        
                
    return x_verified
        
        
    
def _get_missing_extra(x, norm):
    missing = [nk for nk in norm if nk not in x]
    extra = [k for k in x if k not in norm]
    
    return {'missing': missing, 'extra': extra}


def _verify_keys(x, norm, trace, handler):
    me = _get_missing_extra(x,norm)
    mp,ep = '',''
    len_missing,len_extra = len(me['missing']),len(me['extra'])
    if not len_missing + len_extra:
        return me['missing']
    
    if len_missing:
        mp = 'Missing keys: {}'.format(me['missing'])
    if len_extra:
        if len_missing: mp += ', '
        ep = 'Extra keys: {}'.format(me['extra'])
    
    h = handler
    
    if h['missing'] == 'error' and len_missing or h['extra'] == 'error' and len_extra:
        raise KeyError('Trace: {}; {}{}'.format(''.join(trace) + '({})'.format(len(trace)),mp,ep))
    
    elif h['missing'] == 'warn' and len_missing or h['extra'] == 'warn' and len_extra:
        warnings.warn('Trace: {}; {}{}'.format(''.join(trace) + '({})'.format(len(trace)),mp,ep))
        
    return me['missing']


#--------------------------------------

def fill_missing(x, norm):
    return verify_data(x, norm, mode='fill')

#......................................


if __name__ == '__main__':
    print(compare(pd.DataFrame, pd.DataFrame))

    
