from collections import OrderedDict as OD
import pandas as pd
import numpy as np
import datetime as dt
from dateutil.parser import parse as parsedate
import traceback
import warnings
import logging

from fons.errors import (BadInstruction, VeriError, VeriTypeError, 
                         VeriValueError, VeriKeyError, VeriIndexError)

from fons.dict_ops import deep_update
from fons.iter import (flatten, unique)
from fons.pyops import (compare, copy as _copy)
from fons.nan import (nan, Implemented) 

#is_given: nan is NOT implemented
is_given = Implemented()
#is_not_null : nan, None and '_nan_' are NOT implemented
is_not_null = Implemented([None,'_nan_'])
is_null = lambda x: not is_not_null(x)


_EXCEPTIONS = {'type': VeriTypeError,
              'value': VeriValueError,
              'key': VeriKeyError,
              'index': VeriIndexError}

_EXC_MAP = {VeriTypeError: TypeError,
            VeriValueError: ValueError,
            VeriKeyError: KeyError,
            VeriIndexError: IndexError,}


_EXC_ORD = [VeriError, VeriTypeError, VeriValueError, VeriKeyError, VeriIndexError]


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
              [['np.ndarray','numpy.ndarray'],np.array],
              [['dt.date','datetime.date','date'],dt.date],
              [['dt','dt.datetime','datetime.datetime','datetime','datetime64[ns]'],dt.datetime],
              [['td','dt.timedelta','datetime.timedelta','timedelta','timedelta64[ns]'],dt.timedelta],
              [['object'],str],
              [['type'],type],
              [['listlike'],(list,tuple,np.ndarray,pd.Index)],
              [['dictlike'],(dict,OD)]]


MAP = {}
for strnames,func in mappings:
    MAP.update(dict.fromkeys(strnames, func))
    MAP.update({func: func})
    
    
EQUALS = {np.datetime64: pd.Timestamp,
          dt.datetime: pd.Timestamp,
          np.timedelta64: pd.Timedelta,
          dt.timedelta: pd.Timedelta,
          int: np.int32,
          #type(None): pd._libs.tslib.NaTType,
          float: (np.float64, int, np.int32),}

#For checking random objs agains pandas objs
PD_EQUALS = {np.datetime64: pd.Timestamp,
             dt.datetime: pd.Timestamp,
             np.timedelta64: pd.Timedelta,
             dt.timedelta: pd.Timedelta,
             int: float}

"""for k,v in list(EQUALS.items()):
    EQUALS[v] = k"""
    
PD_STRING = {dt.datetime: 'datetime64[ns]',
             np.datetime64: 'datetime64[ns]',
             pd.Timestamp: 'datetime64[ns]',
             dt.timedelta: 'timedelta64[ns]',
             np.timedelta64: 'timedelta64[ns]',
             pd.Timedelta: 'timedelta64[ns]',}



TYPES = ('type','function','module')
_TYPES = tuple([cls for cls in object.__subclasses__() if cls.__name__ in TYPES])

DEFAULT_ARGUMENTS = {dt.date: [(0,0,0),{}],
                     dt.datetime: [(0,0,0),{}],
                     dt.timedelta: [(0,),{}]}

DO_NOT_CALL_BY_DEFAULT = (dt.date, dt.datetime, dt.timedelta)

#may contain dicts of instructions; later are packed into list([inited])/tuple([inited])
#if e.g np.ndarray is preferred, must use {'_type_': np.ndarray, '_call_': np.asarray, 'value'/'_value_': [..instructions..], _kw={'dtype': x}} instead
HANDLEABLES = (list, tuple, set) #?? does `set` belong here?

IMMUTABLES = (int, float, str, bool, tuple, type(None))
CONTAINERS = (dict, list, tuple, set, pd.Series, pd.DataFrame, pd.Index, np.ndarray)
COPY_METHOD = (pd.DataFrame, pd.Series, pd.DatetimeIndex, pd.Index, np.ndarray)


RESERVED = ('_type_', '_call_', '_value_', '_multival_', '_defval_', '_copy_', '_isnorm_', '_multi_')
NORM_EXTRA = {'_type_':str,
              '_value_': '_keep_'}


def _map(item, *default, **kw):
    if not isinstance(item, str):
        if kw.get('pd_dtype'):
            return _map_pd_dtype(item)
        return item
    
    obj = None
    
    if item in MAP:
        obj = MAP[item]
    elif __name__ == '__main__':
        obj = getattr(__builtins__, item, None)
    else:
        obj = __builtins__.get(item, None)
    
    obj_t = (obj,) if not isinstance(obj, tuple) else obj
    
    if any(x is None or type(x).__name__ not in TYPES for x in obj_t):
        if not len(default):
            raise BadInstruction('Item {} not known.'.format(item))
        else:
            return default[0]
    
    if kw.get('pd_dtype'):
        obj = _map_pd_dtype(obj)
    
    #if isinstance(obj,str) and obj != 'datetime64[ns]': raise OSError(obj)
    
    return obj


def _map_pd_dtype(obj):
    try:
        obj = PD_STRING.get(obj, obj)
    except TypeError:
        pass
    return obj


def _isinstructions(x):
    if isinstance(x, Element):
        return True
    elif not isinstance(x, dict):
        return False
    elif not any(k in RESERVED for k in x.keys()):
        return False
    
    return True 


def _isnorm(x):
    if isinstance(x, dict):
        return bool(x.get('_isnorm_'))
    elif isinstance(x, Element):
        return bool(getattr(x, 'isnorm', False))
    
    return False

#---------------------

def normalize(data):
    init_data(data)
    normalized = normalize_element(data)
    
    return normalized


def fill(x, norm, **kw):
    return verify_data(x,norm,mode='fill',**kw)

#----------------------------------------

def init_data(x, copy=True):
    obj = None
    _type = type(x)
    _name = _type.__name__
    
    if issubclass(_type, Element):
        x = x.to_dict()
        _type = dict
    
    if issubclass(_type, dict):
        obj = _init_from_dict(x)
        if copy: obj = _copy(obj)
    
    elif _type not in HANDLEABLES:
        if copy: obj = _copy(x)
        else: obj = x

    else:
        #isinstr = any(_isintruction(y) for y in x)
        #may still contain instructions at a sub-level
        alist = [init_data(y, copy=copy) for y in x]
      
        try:
            call = _map(_name)
            obj = call(alist)
                
        except ValueError:
            obj = alist
            
        except Exception:
            traceback.print_exc()
            obj = alist
        
    return obj



def _init_from_dict(D, copy=True):
    add_to = {}
    if _isinstructions(D):
        return _init_instructions(D, copy=copy)
    
    #initiating its values (plus making copy of the dict)
    for n,v in D.items():
        obj = init_data(v, copy=copy)
        add_to[n] = obj
        #keys are always? immutable, no need to copy
    
    return add_to 



def _init_instructions(D, copy=True):
    normalize_element(D)
    
    if '_copy_' in D:
        if copy:
            return _copy(D['_copy_'])
        else:
            return D['_copy_']
    
    _type_ = D.get('_type_')
    
    if isinstance(_type_, tuple):
        _type0_ = _type_[0]
    else:
        _type0_ = _type_
    
    
    if '_defval_' in D:
        return init_data(D['_defval_'], copy=copy)
    
    elif '_multi_' in D:
        return init_data(D['_multi_'][0], copy=copy)
    
    elif _type0_ in _TYPES:
        #return _map(D.get('_value_'))
        return D.get('_value_')
    
    elif '_value_' in D:
        D['_copy_'] = _copy(D['_value_'])
        return _init_instructions(D, copy=copy)
    
    elif '_multival_' in D:
        D['_copy_'] = _copy(D['_multival_'][0])
        return _init_instructions(D, copy=copy)
    
    
    return _init_by_call(_type0_, D, copy=copy)
    


def _init_by_call(_type_, D, copy=True):
    
    _call0_ = D.get('_call_',nan)

    if is_given(_call0_):
        if is_null(_call0_):
            return nan
            #raise BadInstruction('Wrong _call_: {}'.format(_call0_))
    elif is_null(_type_):
        #return nan
        raise BadInstruction('_type_ is null')
    

    #_value_ is used for not using _call_() or _type_() 
    
    args,kw,_call2_ = [],{},_type_
    
    """if is_null(D.get('args')) and is_null(D.get('kwargs')) and \
            _type_ in DO_NOT_CALL_BY_DEFAULT:
        return nan"""
        
    
    if isinstance(D.get('args'),(list,tuple)):
        args = init_data(D['args'])
    
    if isinstance(D.get('kwargs'),dict):
        kw = init_data(D['kwargs'])
    

    if is_given(_type_) and (not len(args) or not len(kw)): #??
        args2,kw2,_call2_ = _known_types(_type_, D, copy=copy)
        if not len(args):
            args = args2
        kw2.update(kw)
        kw = kw2


    if is_given(_call0_): 
        _call_ = _call0_
    else: 
        _call_ = _call2_
            
    #print(_type.__name__,'args:',args,'kw:',kw)
    obj = _call_(*args,**kw)
    
    
    D['_copy_'] = _copy(obj)

    return obj



def _known_types(_type_, D, copy=True):
    
    #vname = vtype.__name__
    args = []
    kw = {}
    call = _type_
    
    
    if issubclass(_type_, (pd.Series, pd.DataFrame)):
        data = init_data(D.get('data'),copy=False)
        index = init_data(D.get('index'),copy=False)
        dtype = MAP.get(D.get('dtype'))
        
        name = init_data(D.get('name'),copy=False)
        columns = init_data(D.get('columns'),copy=False)
        dtypes = D.get('dtypes')
        
        if _type_ is pd.DataFrame:
            if dtypes:
                if not isinstance(data,dict):
                    data = OD([[c,pd.Series(data, index=index, dtype=_map(d,None,pd_dtype=True))] for c,d in D['dtypes'].items()])
                else:
                    data = OD([[c,pd.Series(data.get(c), index=index, dtype=_map(d,None,pd_dtype=True))] for c,d in D['dtypes'].items()])
            
                if not columns:
                    D['columns'] = list(dtypes.keys())
            
            kw.update({'data':data,'index':index,'columns':columns,'dtype':dtype})
        
        else:
            kw.update({'data':data,'index':index,'name':name,'dtype':dtype})
    
    
    elif issubclass(_type_, dict):
        new_d = {}
        items = []
        
        if is_not_null(D.get('items', nan)):
            items = D['items']
            if isinstance(items,dict):
                items = list(items.items())
        
        elif is_not_null(D.get('keys', nan)):
            keys = D['keys']
            if 'values' in D:
                values = D['values']
            elif 'value' in D or 'v' in D:
                values = [D.get('value',D.get('v'))] * len(keys)
            else:
                values = [D.get('unit')] * len(keys)
            
            items = list(zip(keys,values))
        
        new_d = init_data(items, copy=copy)
        args.append(new_d)
        
        if True:
            D['keys'] = [itm[0] for itm in new_d]
            #For being able to verify_data later (itm[1] -> {'_type_':type(itm[1]),_value_: itm[1])}
            items = [[itm[0],normalize_element(itm[1])] for itm in items]
            D['items'] = items #the instr dicts in items have been normalized due to init_data(items)
            init_data(D.get('unit'), copy=False) #??
    
    
    elif issubclass(_type_, dt.datetime):
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
            raise BadInstruction(_type_, D, value)
    
    
    elif issubclass(_type_, dt.timedelta):
        value = D.get('value', D.get('v'))
        
        if isinstance(value,(list,tuple)):
            args.extend(value)
            
        elif isinstance(value,(int,float)):
            #microseconds
            args.extend([0,0,value*1000])
            
        else:
            raise BadInstruction(_type_, D, value)  
    
    
    elif issubclass(_type_, (list,tuple,set)):
        value = D.get('value', D.get('values', D.get('v', nan)))
        _range = D.get('range', nan)
        size = D.get('size', nan)
        
        if is_not_null(value):
            args.append(init_data(value, copy=copy))
            """if is_null(size):
                D['size'] = {'==': (len(value),)}"""
        
        elif is_not_null(_range) and not isinstance(_range, str):
            arange = list(range(*_range)) #np.arange(*range)
            args.append(arange)
            """if not is_not_null(size):
                D['size'] = {'==': (len(arange),)}"""
            
            if not is_given(value):
                D['value'] = arange
            
            init_data(D.get('unit'), copy=False) #??
    
    
    elif issubclass(_type_, (str,int,float)):
        value = D.get('value', D.get('v'))
        if is_not_null(value):
            args.append(init_data(value))
            D['_value_'] = args[-1]
            #del D['value']
        elif issubclass(_type_, (int, float)) and isinstance(D.get('range'), str):
            limit0, limit1 = D['_range']
            if None not in D['_range']:
                args.append((limit0 + limit1) / 2)
            elif limit0 is not None:
                args.append(limit0)
            elif limit1 is not None:
                args.append(limit1)
    
    else: 
        pass #args.append(init_data(_type_))
    
    #print('args_now:',args)    
    
    return args, kw, call



#--------------------------------------------

def normalize_element(x, default=nan):
    if _isnorm(x): return x
    
    #the corresponding keys' values are treated as literal (if they are present in the x):
    # _defval_, _value_, value, unit, 
    #_call_  :: return _value_/_multival,_defval_ if those present; 
    #            otherwise if _call_ in (None, _nan_ ): return None, else _call_(args), 
    #                and if not given _call_ = _type_. or return None if not is_not_null(_type_)
    
    x_initial = x
    is_element = isinstance(x, Element)
    if is_element:
        x = x.to_dict()
    
    if _isinstructions(x):
        d = x
        _normalize_type(d)
    else:
        d = {'_type_': type(x),
             '_value_': x}
        
    _normalize_defval(d, default)
    
    _normalize_multi(d)
    
    _normalize_value(d)

    _normalize_call(d)
        
    _normalize_size(d)
    _normalize_range(d)
    
    _normalize_unit(d)
    
    _normalize_dtypes(d)
    _normalize_opt_req(d)
    
    _type_ = d.get('_type_',nan)
    if is_given(_type_):
        if isinstance(_type_, tuple):
            _type_ = _type_[0]
        
        if not issubclass(_type_, (dt.datetime, dt.timedelta)):
            _known_types(_type_, d, copy=False)
    
    d['_isnorm_'] = True
    
    if is_element:
        x_initial.update(d, normalize=False)
        return x_initial
    
    return d


def _normalize_type(d):
    _type_ = d.get('_type_')
        
    if is_null(_type_):
        d.pop('_type_',-1)
        return
            
    if isinstance(_type_, MAP['listlike']):
        _type_ = tuple((_map(t) for t in _type_))
    else:
        _type_ = _map(_type_)
    
    if isinstance(_type_, tuple):
        for t in _type_:
            _verify_is_type(t)
    else:
        _verify_is_type(_type_)
    
    d['_type_'] = _type_


def _normalize_defval(d, default):
    if default is not nan:
        d['_defval_'] = normalize_element(default)
    elif '_defval_' in d:
        d['_defval_'] = normalize_element(d['_defval_'])


def _normalize_multi(d):
    _multi_ = d.get('_multi_',nan)
    if is_null(_multi_): 
        d.pop('_multi_', -1)
    elif isinstance(_multi_, MAP['listlike']):
        if len(_multi_):
            _multi_ = list(_multi_)
            for i,d2 in enumerate(_multi_):
                _multi_[i] = normalize_element(d2)
                init_data(_multi_[i], copy=False)
        else:
            del d['_multi_']
    else:
        raise BadInstruction('Defective "_multi_": {}'.format(_multi_))


def _normalize_value(d):
    if _isinstructions(d.get('_value_')):
        d['_value_'] = init_data(d['_value_'], copy=False)
    
    has_type_key = '_type_' in d
    _type_ = d.get('_type_')
    
    add_types = []
    sub_allowed = d.get('sub', d.get('sub_allowed')) is not False
    
    #Value can be anything but fons.nan.nan
    if '_value_' in d and not is_given(d['_value_']):
        d.pop('_value_',-1)
    
    _value_ = d.get('_value_')
    
    if '_value_' in d:
        if is_not_null(_value_) and has_type_key:
            d['_value_'] = _map_value_if_str(_type_, _value_)
            
        add_types.append(type(d['_value_']))
        
        
    _multival_ = d.get('_multival_',nan)
    if is_null(_multival_):
        d.pop('_multival_',-1)
    elif isinstance(_multival_, MAP['listlike']):
        if len(_multival_):
            inited = [init_data(v, copy=False) for v in _multival_]
            multival = [_map_value_if_str(_type_, v) 
                            if has_type_key and is_not_null(v) else 
                        v for v in inited]
            add_types += [type(x) for x in multival]
            if '_value_' in d:
                multival.insert(d['_value_'], 0)
                del d['_value_']
            d['_multival_'] = multival
        else:
            del d['_multival_']
    else:
        raise BadInstruction('Defective "_multival_": {}'.format(_multival_))
    
    
    if add_types:
        types = ((_type_,) if not isinstance(_type_, tuple) else _type_)  if has_type_key else ()
        for x in add_types:
            if not types : pass
            elif sub_allowed and not issubclass(x, types): pass
            elif not sub_allowed and x not in types: pass
            else: continue
            types += (x,)
        
        if types:
            d['_type_'] = types if len(types) > 1 else types[0]


def _map_value_if_str(_type_, _value_):
    if is_null(_type_):
        return _value_
    #to map e.g {'_type_: type, '_value_': 'list'} to {'_value_': list} 
    # for (normalized) init and compare purposes
    t_types = _type_ if isinstance(_type_,tuple) else (_type_,)
    if isinstance(_value_, str) and not any(issubclass(t,str) for t in t_types):
        return _map(_value_)
    else:
        return _value_


def _normalize_call(d):
    if '_call_' not in d: pass
    elif is_not_null(d['_call_']): #??
        d['_call_'] = _map(d['_call_'])


def _normalize_size(d):
    size = d.get('size',nan)
    if is_null(size):
        d.pop('size',-1)
    elif not isinstance(size, (int, dict)):
        raise BadInstruction('"size" must be int/dict; got: {}'.format(type(size)))
    elif isinstance(size, int):
        d['size'] = {'exact': size}
    else:
        for arg in ('min','max','exact'):
            value = size.get(arg)
            if value is None: continue
            elif not isinstance(value, int):
                raise BadInstruction('"size" keyword "{}" must be of type int; got: {}'.format(
                    arg, type(value)))


def _parse_number(x):
    if not x or x=='null':
        return None
    try: 
        return float(x)
    except ValueError:
        return '?'


def _normalize_range(d):
    range = d.get('range',nan)
    if is_null(range):
        d.pop('range',-1)
    # range for verifying int/float
    elif isinstance(range,str):
        first, middle, last = range[:1], range[1:-1], range[-1:]
        _range = tuple(_parse_number(x.strip()) for x in middle.split(','))
        correct = '?' not in _range
        all_num = all(isinstance(x, float) for x in _range)
        if not range or first not in '[(' or last not in '])' or len(_range)!=2 or not correct \
                or all_num and _range[0]>_range[1]:
            raise BadInstruction('Not understood scalar "range": {}'.format(range))
        d['_range'] = _range
    # range for list/tuple/set initiation
    elif isinstance(range,int):
        d['range'] = (0,range)
    elif not isinstance(range, MAP['listlike']):
        raise BadInstruction('Wrong type for "range": {}'.format(type(range)))
    elif len(range) != 2:
        raise BadInstruction('Wrong size for "range": {}'.format(len(range)))
    elif not isinstance(range[0],int) or not isinstance(range[1],int):
        raise BadInstruction('"range" contains non-int type: {}'.format([type(y) for y in range]))


def _normalize_unit(d):
    if 'unit' in d:
        d['unit'] = normalize_element(d['unit'])
        init_data(d['unit'], copy=False)


def _normalize_dtypes(d):
    dtypes = d.get('dtypes', nan)
    if is_null(dtypes):
        if 'dtypes' in d:
            del d['dtypes']
        return
    if is_null(d.get('_type_', nan)):
        raise BadInstruction('_type_ must be given if "dtypes" is defined; d: {}'.format(d))
    _type = _map(d['_type_'])
    if not isinstance(_type, tuple):
        _type = (_type,)
    for_dict = any(issubclass(x, dict) for x in _type)
    for_pandas = any(issubclass(x, (pd.Series, pd.DataFrame)) for x in _type)
    items = []
    default_dtype = d.get('default_dtype', None)
    
    if not isinstance(dtypes,dict):
        d['dtypes'] = dtypes = OD(dtypes)
    
    for k,v in dtypes.items():
        if not _isinstructions(v):
            dd = {'_type_': _map(v, pd_dtype=for_pandas)}
            normalize_element(dd, default=default_dtype)
        else: 
            dd = v #normalize_element(v) #don't use default=v, inf recursion
        
        if for_pandas:
            if isinstance(dd, Element):
                dd = dd.to_dict()
            _type_ = dd.get('_type_')
            _type_mapped = _map(_type_, pd_dtype=True)
            if is_null(_type_) or not isinstance(_type_mapped, (type, str)):
                raise BadInstruction('Pandas dtype _type_ is invalid: /k: v/: {}: {} || type(v): {}'.format(k, v, type(v)))
            dtypes[k] = _type_mapped
        
        if for_dict:
            items.append([k, dd])
    
    if for_dict and is_null(d.get('items',nan)):
        d['items'] = items


def _normalize_opt_req(d):
    # all keys that aren't in required (if given) are optional
    # use 'required' if nearly all keys are optional
    aliases = {
        'optional': ['opt','optional','keys_optional'],
        'required': ['req','required','keys_required'],
    }
    for key, aliases in aliases.items():
        final = nan
        for alias in aliases:
            value = d.pop(alias, nan)
            if is_null(value):
                pass
            elif not isinstance(value, MAP['listlike']+(dict,)):
                raise BadInstruction('Wrong type for "{}": {}'.format(alias, type(value)))
            elif final is not nan:
                raise BadInstruction('Got multiple values for {}'.format(key))
            else:
                final = value
        if is_not_null(final):
            d[key] = final

#-------------------------------------
#type - error/warn/ignore/fix/fix+
#value - error/warn/ignore/fix/fix+
#//use-this for (list-e, dict-e):
#missing - error/warn/ignore/fix/fix+
#extra - error/warn/ignore/fix/fix+

#//explanation: 
#fix - replace (existing), add (missing) with newly initiated element, if its _call_ is not None or value is specified, otherwise raise error;
#    - delete (extra element)
#fix- - fix and DON'T warn

#///too-complicated:
#list_e - {'missing': error/warn/ignore/fix/fix+,
#           'extra': error/warn/ignore/fix/fix+,
#           'value': error/warn/ignore/fix/fix+}
#dict_e - {'missing': error/warn/ignore/fix/fix+,
#           'extra': error/warn/ignore/fix/fix+,
#           'value': error/warn/ignore/fix/fix+}

#copy:
# 'fix_mode' - the object (x) is copied only if any of the handler modes is set to 'fix'/'fix-'
# True - obj is always copied
# False - obj is modified inplace, if mode == 'fix/fix-'
#         however some defective objects are still "copied" in these cases:
#             - type mismatch between the obj and norm
#             - the obj is immutable
#             - copying it/making new one is considerably faster than modifying inplace (eg adding dataframe missing columns one by one)
#         therefore user should always overwrite x = verify_data(x), and still update all the references


_MODES = ('error','warn','ignore','fix','fix-')
_ERROR_MODES = ('error',)
_FIX_MODES = ('fix','fix-')
_WARN_MODES = ('warn','fix')

_HANDLER_KEYS = ('type','value','key','index')
_H_OBJ_KEYS = ('type','value')
_H_CONTAINER_KEYS = ('key','index')
_H_CONTAINER_OPTIONS = ('missing','extra')


def verify_data(x, norm, mode='error', copy=False, **kw):
    if copy:
        x = _copy(x)
    copy = False
    
    if not _isnorm(norm):
        norm = normalize_element(norm)
        init_data(norm, copy=False)
    
    if isinstance(norm, Element):
        norm = norm.to_dict()
    
    kw.update({'mode': mode})#, 'copy': copy})
    norm_extra = kw.get('norm_extra', nan)
    trace = kw.get('trace',[])
    
    _verify_input_args(kw)
    handler = kw['handler']
    #copy = kw['copy']

    x_ver = x
    
    if is_not_null(norm_extra):
        try: 
            verify_data(x_ver, norm_extra, 'error', trace=trace)
            #if _isinstructions(kw['norm_extra']): verify_data(x_ver,norm_extra,**kw)
            #else: verify_data(x_ver,normalize_element({},default=norm_extra),**kw)
        except Exception: 
            pass
        else: 
            return x_ver #passed[:] = True
        
    
    _defval_ = norm.get('_defval_', nan)
    sub_allowed = norm.get('sub', norm.get('sub_allowed')) is not False
    
    if is_not_null(_defval_): 
        if _verify_defval(x_ver, _defval_, sub_allowed=sub_allowed):
            return x_ver
    
    
    _multi_ = norm.get('_multi_', nan)
    
    if is_not_null(_multi_) and len(_multi_):
        return _verify_multi(x_ver, _multi_, mode, trace, handler, copy)
    
    
    #---------------------------------------------------------------
    #---------------------------------------------------------------
    _type = type(x)
    t_name = _type.__name__
    len_trace = len(trace)
    trace2 = trace + ['({}){}'.format(len_trace, t_name)]
    
    if not len_trace and copy:
        x_ver = init_data(x, copy=True) #done many times if _multi_ specified
    else:
        x_ver = x
    
    passed = pd.Series(True, ['type','value','range'])
    
    
    #-type-
    normtype = norm.get('_type_', nan)
    
    if is_not_null(normtype):
        r = _verify_type(_type, normtype, sub_allowed)
        if r is not True: 
            _handle_error(handler, 'type', [trace2, t_name, r])
            passed.type = False
    
    
    #-value-
    has_value = '_value_' in norm
    _multival_ = norm.get('_multival_', nan)
    
    if has_value:
        _value_ = norm.get('_value_')
        passed.value = compare(x_ver, _value_, type_op='ignore')
        if not passed.value:
            _handle_error(handler, 'value', [trace2, x_ver, _value_])
    
    elif is_not_null(_multival_):
        passed.value = any(compare(x_ver, val, type_op='ignore') for val in _multival_)
        if not passed.value:
            _handle_error(handler, 'value', [trace2, x_ver, _multival_])
    
    else:
        try: iter(x_ver)
        except TypeError: pass
        else: 
            x_ver = _verify_elements(x_ver, norm, mode, trace2, handler, copy)
    
    
    #-range-
    range = norm.get('range')
    if isinstance(x_ver, (int, float)) and is_not_null(range) and isinstance(range, str):
        passed.range = _verify_in_range(x_ver, norm)
        if not passed.range:
            _handle_error(handler, 'value', [trace2, x_ver, 'in range: {}'.format(range)])
    
    
    if not passed.all():
        x_ver = init_data(norm)
        
        
    return x_ver


def _verify_defval(x, _defval_, **kw):
    _type = type(x)
    try:
        _type1 = _defval_['_type_']
    except Exception as e:
        print(x, _defval_, kw)
        raise e
    _type1a = EQUALS.get(_type1) if not isinstance(_type1,tuple) else tuple((EQUALS.get(t2) for t2 in _type1))
    
    correct_types = _flatten_types(_type1, _type1a)
    sub_allowed = _defval_.get('sub', _defval_.get('sub_allowed'))
    defval_sub_allowed = False if sub_allowed is False else kw.get('sub_allowed',True)
    
    r = _verify_type(_type, correct_types, sub_allowed=defval_sub_allowed)
    
    if r is not True: pass
    elif not compare(x, init_data(_defval_, copy=False), type_op='ignore'): pass
    #print('Compare UNSUCCESSFUL! {} {}'.format(x,_defval_)
    else: return True
    
    return False


def _verify_multi(x, _multi_, mode, trace, handler, copy=False):
    exceptions = []
    passed = False
    
    for norm in _multi_:
        try:
            x_ver = verify_data(x, norm, 'error', trace=trace)
            passed = True
        except VeriError as e:
            exceptions.append(e)
        else:break
    
    if not passed:
        dx = _handle_error(handler, exceptions) #may raise (if deepest lvl error's mode in handler is 'error')
        is_fix = dx['is_fix']
        
        if is_fix: 
            most_similar_norm = _multi_[dx['i']] #i is the index of the first deepest level error
            x_ver = verify_data(x, most_similar_norm, mode, copy, trace=trace, handler=handler)
 
        #A drawback of singling out -> _multi: [{'_type_:xr}, {'_type_':x}] only shows the first e msg
        #raise VeriError('Verification failed. The following exceptions occurred: {}'.format(exceptions))
        
    return x_ver


def _verify_in_range(x, norm):
    range = norm['range']
    limit0, limit1 = norm['_range']
    
    if limit0 is not None:
        result0 = limit0 <= x if range[0]=='[' else limit0 < x
        if not result0:
            return False
    
    if limit1 is not None: 
        result1 = x <= limit1 if range[-1]==']' else x < limit1
        if not result1:
            return False
    
    return True

#-------------------------------------------------------------
    
def _verify_elements(x, norm, mode, trace, handler, copy=False):
    pdlike = (pd.Series, pd.DataFrame)
    _check_size(x, norm, trace, handler)

    if isinstance(x, dict):
        x_ver = _verify_dict(x, norm, mode, trace, handler, copy)

    elif isinstance(x, pdlike):
        x_ver= _verify_pandaslike(x, norm, mode, trace, handler, copy) 
            
    else: #if isinstance(x,(list,tuple,set)) or is_iterable:
        x_ver = _verify_listlike(x, norm, mode, trace, handler, copy)

                          
    return x_ver


def _verify_dict(x, norm, mode, trace, handler, copy=False):
    fix_vals = handler['type'] in _FIX_MODES or handler['value'] in _FIX_MODES
    
    unit = norm.get('unit',nan)
    extra_allowed = norm.get('extra_allowed')
    keys_opt = norm.get('optional',[])
    keys_req = norm.get('required',nan)
    
    nitems = norm.get('items')
    
    if nitems:
        nkeys = [itm[0] for itm in nitems]
        me = _verify_keys(x.keys(), nkeys, trace, handler, keys_opt, keys_req, extra_allowed)
        
        if handler['key']['missing'] in _FIX_MODES and len(me['missing_all']):
            #messes up order if OD
            n_inited = init_data(norm,copy=False)
            #if len(missing): print(trace,'missing:',missing)
            x.update({_copy(k):_copy(v) for k,v in n_inited.items() if k in me['missing_all']})
            
        for nk,nv in nitems:
            if nk in me['missing_all']:continue
            trace2 = trace[:-1] + [''.join(trace[-1:]) + '({})(key){}'.format(len(trace),nk)]
            xv = verify_data(x[nk], nv, mode, trace=trace2, handler=handler)
            if fix_vals: x[nk] = xv
        
        if handler['key']['extra'] in _FIX_MODES and len(me['extra']):
            for ke in me['extra']:
                x.pop(ke)

    if is_not_null(unit):
        for k,v in x.items():
            trace2 = trace[:-1] + [''.join(trace[-1:]) + '({})(key){}'.format(len(trace),k)]
            xv = verify_data(v, unit, mode, trace=trace2, handler=handler)
            if fix_vals: x[k] = xv
             
    return x


def _verify_pandaslike(x, norm, mode, trace, handler, copy=False):
    unit = norm.get('unit',nan)
    extra_allowed = norm.get('extra_allowed')
    keys_opt = norm.get('optional',[])
    keys_req = norm.get('required',nan)
    
    is_series = isinstance(x,pd.Series)
    is_df = isinstance(x,pd.DataFrame)
    
    ndtype0 = norm.get('dtype',nan)
    ndtypes = norm.get('dtypes',nan)
    #dtypes = x.dtypes
    inplace = not(copy)
    
    wrong_dtypes = []
    dtypes = x.dtypes.iteritems() if is_df else [(x.name,x.dtype)]
    
    for c,itm in dtypes:
        dtype = _map(itm.name, pd_dtype=True)
        if is_not_null(ndtype0):
            ndtype = ndtype0 
        elif is_not_null(ndtypes) and c in ndtypes:
            ndtype = ndtypes[c]
        else: continue
        
        #both may be strings (datetime64[ns])
        #however. int may be float
        if dtype != ndtype and dtype is not PD_EQUALS.get(ndtype):
            wrong_dtypes.append({c:(dtype,ndtype)})
     
    nr_wrong = len(wrong_dtypes)    
            
    if nr_wrong:
        trace2 = trace + ['({})(dtypes)'.format(len(trace))]
        _handle_error(handler, 'type', [trace2, wrong_dtypes])
            
    if nr_wrong and handler['type'] in _FIX_MODES:
        for c, tpl in wrong_dtypes:
            dtype,ndtype = tpl
            try:
                if is_df: x[c] = x[c].astype(ndtype)
                else: x = x.astype(ndtype)
            except Exception as e:
                logging.exception(e)
            
            
    ncols = norm.get('columns')
    nindex = norm.get('index')
    
    _keys = ('missing','extra','missing_all','extra_all')
    me_cols = {_k: [] for _k in _keys}
    me_ind = {_k: [] for _k in _keys}
    
    if isinstance(keys_opt,dict):
        index_opt = keys_opt.get('index')
        cols_opt = keys_opt.get('columns')
    else: index_opt = cols_opt = []
    
    if isinstance(keys_req,dict):
        index_req = keys_req.get('index')
        cols_req = keys_req.get('columns')
    else: index_req = cols_req = nan
    
    if isinstance(extra_allowed,dict):
        ea_index = extra_allowed.get('index')
        ea_cols = extra_allowed.get('columns')
    else: ea_index = ea_cols = extra_allowed
    
    if is_df and ncols is not None:
        me_cols = _verify_keys(x.columns, ncols, trace, handler, cols_opt, cols_req, ea_cols)
        
    if nindex is not None:
        me_ind = _verify_keys(x.index, nindex, trace, handler, index_opt, index_req, ea_index)
    
    if handler['key']['missing'] not in _FIX_MODES: pass
    elif len(me_ind['missing']) or len(me_cols['missing']):
        x_new = init_data(norm)
        if not inplace: #much faster
            if is_series: x_new.loc[x.index] = x
            else: x_new.loc[x.index,x.columns] = x  #(this doesn't link the old x's values with x_new)
            x = x_new
    
        else:
            for c in me_cols['missing']:
                pos = next((j for j in ncols if j == c),x.shape[1])
                x.insert(pos, c, x_new[c])
                
            if is_df:
                for i in me_ind['missing']:
                    pos = next((j for j in nindex if j == i),x.shape[0])
                    x.insert(pos, i, x_new.loc[i,:],axis=1)
            else:
                for i in me_ind['missing']:
                    x[i] = x_new[i]

        
    if handler['key']['extra'] in _FIX_MODES:
        if len(me_ind['extra']): 
            if inplace: x.drop(me_ind['extra'], inplace=True)
            else: x = x.drop(me_ind['extra'])
        if len(me_cols['extra']):
            if inplace: x.drop(me_cols['extra'], axis=1, inplace=True)
            else: x = x.drop(me_cols['extra'], axis=1)
          
    return x
            
     
             
def _verify_listlike(x, norm, mode, trace, handler, copy=False):
    if isinstance(x, set):
        new = _verify_set_elements_by_nvalue(x, norm, mode, trace, handler)
    else:
        new = _verify_list_elements_by_nvalue(x, norm, mode, trace, handler)
    
    unit = norm.get('unit', nan)
                  
    if is_not_null(unit):
        new = [verify_data(v, unit, mode, trace=trace, norm_extra=NORM_EXTRA, handler=handler)
                for v in new]
            
    #if only unit is given, and e.g `unit = {'_type_': dt, '_call_': None}`, `mode = 'fill'` doesn't replace the wrong values with None
    #(mode 'fill' does and will only work for *missing* data, with either _dict_ attr present, or listlike with endings capped)
    
    if is_not_null(new): #and any(m in _FIX_MODES for m in handler.values()):
        #deepcopy norm_new?
        norm_new = {k: norm[k] for k in norm if k not in ('_copy_',)}
        norm_new.update({'values': new}) #,'_value_':None})
        x = init_data(norm_new)
    
    return x


def _verify_set_elements_by_nvalue(x, norm, mode, trace, handler):
    extra_allowed = norm.get('extra_allowed')
    nvalue = norm.get('value', norm.get('values', norm.get('v', nan)))
    if is_null(nvalue):
        return x
    
    missing = set(_ for _ in nvalue if _ not in x)
   
    if not missing: pass
    elif handler['index']['missing'] in _FIX_MODES:
        x.update(set(_copy(_) for _ in missing))
    else:
        _handle_error(handler, 'value', [trace, nan, 'missing:{}'.format(missing)])
    
    if not extra_allowed:
        extra = set(_ for _ in x if _ not in nvalue)
        if not extra: pass
        elif handler['index']['extra'] in _FIX_MODES:
            for _ in extra:
                x.pop(_)
        else:
            _handle_error(handler, 'value', [trace, 'extra:{}'.format(extra)])
            
    return x


def _verify_list_elements_by_nvalue(x, norm, mode, trace, handler):
    extra_allowed = norm.get('extra_allowed')
    nvalue = norm.get('value', norm.get('values', norm.get('v', nan)))
    if is_null(nvalue):
        return x
    
    len_x, len_nv = len(x), len(nvalue)
    _min_len = min(len_x,len_nv)
    norm_extra = NORM_EXTRA #?? Should this be deprecated?
    #if sizes differ then zip will only iterate to the lowest size
    new = x[:_min_len]
    
    if len_x < len_nv:
        if handler['index']['missing'] in _FIX_MODES:
            x_new = init_data(norm, copy=False)
            new += _copy(x_new[len_x:])
        else:
            _handle_error(handler, 'value', [trace, nan, 'missing:{}'.format(nvalue[len_x:])])
    
    if len_x > len_nv and not extra_allowed:
        if handler['index']['extra'] not in _FIX_MODES:
            _handle_error(handler, 'value', [trace, 'extra:{}'.format(x[len_nv:])])
            new += x[len_nv:]
            
    new = [verify_data(v, nv, mode, trace=trace, handler=handler, norm_extra=norm_extra)
           for v,nv in zip(new[:_min_len],nvalue)] + new[_min_len:]
    
    return new


#-----------------------------------------------------------------------

def _verify_type(_type, correct_types, sub_allowed=True, **kw):
    ctps = correct_types
    ctps2 = EQUALS.get(ctps) if not isinstance(ctps,tuple) else tuple((EQUALS.get(t1) for t1 in ctps))
    #Note that due to normalisation norm['_type'] is always hashable (is either type or tuple or types)
    
    correct_types = _flatten_types(ctps, ctps2)
    #as_dict = kw.get('as_dict')
    
    if sub_allowed and not issubclass(_type, correct_types): pass
    elif not sub_allowed and _type not in correct_types: pass
    else: return True
    
    return correct_types


def _get_missing_extra(x, norm):
    missing = tuple(filter(lambda nk: nk not in x, norm))
    extra = tuple(filter(lambda k: k not in norm, x))
    
    return {'missing': missing, 'extra': extra}


def _verify_keys(x, norm, trace, handler, optional=[], required=None, extra_allowed=False):
    me = _get_missing_extra(x,norm)
    extra = tuple(filter(lambda k: k not in optional, me['extra'])) if not extra_allowed else tuple()
    missing = tuple(filter(lambda k: k not in optional, me['missing']))
    if is_not_null(required):
        missing = tuple(filter(lambda k: k in required, missing))
    
    len_missing,len_extra = len(missing),len(extra)
    if not len_missing + len_extra:
        return {'missing': missing, 'extra': extra, 'missing_all': me['missing'], 'extra_all': me['extra']}
    
        
    mp = missing if len_missing else nan
    ep = extra if len_extra else nan
    
    trace2 = trace + ['({})'.format(len(trace))]
    _handle_error(handler, 'key', [trace2, ep, mp])
        
    return {'missing': missing, 'extra': extra, 'missing_all': me['missing'], 'extra_all': me['extra']}


def _check_size(x, norm, trace, handler):
    size = norm.get('size')
    if is_null(size):
        return True
    
    len_x = len(x)
    all_correct = True
    
    for arg,op in [('min',lambda y: len_x>=y),
                   ('max',lambda y:len_x<=y),
                   ('exact',lambda y: len_x==y)]:
        limit = size.get(arg)
        if is_null(limit): continue
        satisfied = op(limit)
        all_correct = min(all_correct, satisfied)
        if not satisfied:
            _handle_error(handler, 'index', [trace, len_x, '{}:{}'.format(arg,limit)])
            
    return all_correct


def _check_size2(x, norm, trace, handler):
    size = norm.get('size',nan)
    if not is_not_null(size):
        return True
    
    size = norm.get('size')
    incl = size.get('include',nan)
    excl = size.get('exclude',nan)
    len_x = len(x)
    is_correct = False
    
    if is_not_null(excl) and len_x in excl:
        _handle_error(handler, 'index', [trace,'({}, excl:{})'.format(len_x, excl)])
         
    elif is_not_null(incl) and len_x not in incl:
        _handle_error(handler, 'index', [trace,'({}, incl:{})'.format(len_x, excl)])
            
    else: is_correct = True
            
            
    return is_correct
    

#-------------------------------------------------------------------------------------------------

def _flatten_types(_types, _equals=None):
    try: _types = tuple(flatten(_types))
    except TypeError: _types = (_types,)
    
    try: _equals = tuple(flatten(_equals))
    except TypeError: _equals = (_equals,)
    
    f = lambda x: x is not None
    
    return tuple(unique(filter(f, _types + _equals)))


def _verify_is_type(x):
    if not type(x) is type:
        raise BadInstruction('Is not type: {}'.format(x))
    
    return x


def _verify_input_args(kw):
    handler = kw.get('handler',{})
    if _isnorm(handler): return kw
    elif not isinstance(handler,dict):
        raise TypeError('Handler must be dict, instead got: {}'.format(type(handler).__name__))
    
    mode = kw['mode']
    if kw['mode'] not in _MODES:
        raise ValueError('Wrong mode: {}'.format(mode))
    
    fix_any = mode in _FIX_MODES
    
    #--else--:
    
    for k in _H_OBJ_KEYS:
        hx_mode = handler.get(k, kw.get(k,mode))
        if hx_mode in _FIX_MODES:
            fix_any = True
        elif hx_mode not in _MODES:
            raise ValueError('Wrong "{}" mode: {}'.format(k, hx_mode))
        handler[k] = hx_mode
    
    #{'key': {'extra': _mode, 'missing': _mode2}, 'index': ...} 
    by_mode = {c: {x: mode for x in _H_CONTAINER_OPTIONS} for c in _H_CONTAINER_KEYS}
    by_option = {c: {x: kw.get(x) for x in _H_CONTAINER_OPTIONS} for c in _H_CONTAINER_KEYS}
    by_type = {c: {x: kw.get(c) for x in _H_CONTAINER_OPTIONS} for c in _H_CONTAINER_KEYS}
    by_handler = {c: {x: handler.get(c, {}).get(x) for x in _H_CONTAINER_OPTIONS} for c in _H_CONTAINER_KEYS}
    
    hierarchy = {None: {'doms': 'all'}} #do not overwrite with None
    for x in (by_mode, by_option, by_type, by_handler):
        deep_update(handler, x, False, hierarchy)

    
    for c in _H_CONTAINER_KEYS:
        for x in _H_CONTAINER_OPTIONS:
            cx_mode = handler[c][x]
            if cx_mode in _FIX_MODES:
                fix_any = True
            elif cx_mode not in _MODES:
                raise ValueError('Wrong "{}" mode: {}; kwargs: {}'.format(c, cx_mode, kw))
            
    """for k in _H_CONTAINER_KEYS:
        hx_mode = handler.get(k) #, kw.get(k,mode)
        if hx_mode is None:
        if isinstance(hx_mode,str):
            if hx_mode in _MODES:
                if hx_mode in _FIX_MODES:
                    fix_any = True
                handler[k] = hx_mode = dict.fromkeys(_H_CONTAINER_OPTIONS, hx_mode)
            else:
                raise ValueError('Wrong "{}" mode: {}'.format(k, hx_mode))
        
        elif not isinstance(hx_mode,dict):
            raise TypeError('Wrong type for "{}" mode: {}'.format(k, type(hx_mode).__name__))
        
        d = hx_mode
        for k2 in _H_CONTAINER_OPTIONS:
            hox_mode = d.get(k2, handler.get(k2, kw.get(k2,mode)))
            if hox_mode in _FIX_MODES:
                fix_any = True
            elif hox_mode not in _MODES:
                raise ValueError('Wrong "{}":{} mode: {}'.format(k, k2, hox_mode))
            d[k2] = hox_mode
            
        handler[k] = d"""
        
        
    handler['_isnorm_'] = True
    kw['handler'] = handler
    
    
    """copy = kw['copy']
    if type(copy) is bool: pass
    elif isinstance(copy,str): pass
    else: raise TypeError('Wrong type for "copy" argument: {}'.format(type(copy)))
    
    if copy == 'fix_mode':
        if fix_any: copy = True
        else: copy = False
        
    kw['copy'] = copy"""
        
        
    for k in list(kw.keys()):
        if k not in ('handler','mode','copy'):
            del kw[k]
            


def _single_out(errors):
    #higher is more specific
    def _get_error_rank(e):
        return _EXC_ORD.index(type(e))
    
    def _update(e, rank, lvl, i):
        e_inf.update({'errors': [e], 'rank': rank, 'lvl': lvl, 'i': i+1})
    
    _errors = errors
    e_inf = {'errors': [_errors[0]],
             'rank': _get_error_rank(errors[0]),
             'lvl': errors[0].level,
             'i': 0}
    
    for i,e in enumerate(errors[1:]):
        rank = _get_error_rank(e)
        lvl = e.level #_get_trace_lvl(e)
        
        if lvl > e_inf['lvl']:
            _update(e, rank, lvl, i)
        
        elif lvl == e_inf['lvl']:
            if rank > e_inf['rank']:
                _update(e, rank, lvl, i)
            elif rank == e_inf['rank']: 
                e_inf['errors'].append(e)


    errors = e_inf['errors']
    
    if len(errors) == 1:
        return {'e': errors[0], 'i': e_inf['i']}
    
    e_args = []
    msgs = []
    for i,e in enumerate(errors):
        #if i > 0: e.args[0] = " ".join(e.args[0].split(" ")[1:])
        #the first arg begins with trace, which'll be identical for same lvl same type errors

        #e_args.extend(e.args)
        e_args = e.args
        msgs.append(e.msg)
    
    new_e = errors[0].__class__(*e_args) #??
    new_e.msg = " || ".join(msgs)
    
    return {'e': new_e, 'i': e_inf['i']}
    

"""def _get_trace_lvl(e):
    msg = e.args[0]
    trace = msg.split(" ")[0]
    
    lvl = 0
    
    for i,c in enumerate(trace):
        if c!= "(": continue
        i2 = next(((i+1)+j for j,c2 in enumerate(trace[i+1:]) if not c2.isdigit()),-1)
        if i2 in (-1,i+1) or trace[i2] != ")": continue
        
        lvl2 = int(trace[i+1:i2])
        if lvl2 != lvl + 1: continue
        
        lvl = lvl2
        
    return lvl"""


def _handle_error(handler, type, args=[], kw={}):
    e, i = (None, 0)
    
    if isinstance(type,VeriError): 
        e = type
    elif isinstance(type,(list,tuple)):
        if len(type) > 1:
            d = _single_out(type)
            e,i = d['e'],d['i']
        else: e = type[0]
        
    if e is not None: 
        type = e.type
    
    mode = handler[type]
    ms = None
    
    if not isinstance(mode,dict):
        ms = _mode_specs(mode)
    
        if not (ms['is_error'] or ms['is_warn']):
            return {'i': i, 'is_fix': ms['is_fix']}
    

    if e is None:
        eclass = _EXCEPTIONS[type]
        e = eclass(*args,**kw)
        
    if ms is None:
        ms = _mode_specs_from_error(e, handler)
        
    
    if ms['is_error']:
        raise e
    elif ms['is_warn']:
        warnings.warn(str(e))
    
    return {'i': i, 'is_fix': ms['is_fix']}
    


def _mode_specs(mode):
    if mode is None:
        return dict.fromkeys(('is_error','is_fix','is_warn'), False)
        
    is_error = mode in _ERROR_MODES
    is_warn = False if is_error else mode in _WARN_MODES
    is_fix = False if is_error else mode in _FIX_MODES
    
    return {'is_error': is_error, 'is_fix': is_fix, 'is_warn': is_warn}


def _mode_specs_from_error(e,handler):
    is_faulty = e.is_faulty()
    x = handler[e.type]
    
    if is_faulty is True:
        return _mode_specs(x)
    elif is_faulty is False:
        return _mode_specs(None)
    
    #-else is_faulty is dict
    
    specs = _mode_specs(None)
    
    for subset,f_val in is_faulty.items():
        if not f_val: continue
        
        e_mode = x[subset]
        new_specs = _mode_specs(e_mode)
        specs.update({k:v for k,v in new_specs.items() if v})
        
        
    return specs
        
    

def convert_exception(e):
    t = _EXC_MAP.get(type(e))
    if not t:
        return e
    
    return t(e.msg)



#--------------------------------------

def fill_missing(x, norm, warn=True):
    mode = 'fix' if warn else 'fix-'
    return verify_data(x, norm, mode=mode)

#......................................

def _resolve(x, as_type=False):
    if _isinstructions(x):
        return x
    if as_type:
        e = None
        try: 
            d = {'_type_': x}
            _normalize_type(d)
            if '_type_' in d:
                return d
            e = BadInstruction('Does not resolve to type: {}'.format(x))
        except BadInstruction as exc:
            e = exc
        if e and as_type!='try':
            raise e
    return {'_value_': x}


class Element:
    __aliases = {
        'type': ['_type_', 'type'],
        'value': ['_value_', 'value'],
        'multival': ['_multival_', 'multival'],
        'defval': ['_defval_', 'defval'],
        'unit': ['unit'],
        'dtypes': ['dtypes'],
        'default_dtype': ['default_dtype'],
        'call': ['_call_', 'call'],
        'keys': ['keys'],
        'values': ['values', 'v'],
        'items': ['items'],
        'multi': ['_multi_','multi'],
        'isnorm': ['_isnorm_','isnorm'],
    }
    
    def __init__(self, *type, **kw):
        self.verify_params(type, kw)
        if len(type):
            self.type = type[0] if len(type) == 1 else type
        
        self.update(kw)
    
    
    def __call__(self, copy=True):
        return init_data(self, copy=copy)
    
    
    def verify(self, x, mode='error', copy=False, **kw):
        return verify_data(x, self, mode, copy, **kw)
    
    
    def to_dict(self, **kw):
        if hasattr(self, '__dict') and not kw:
            return self.__dict
        d = {}
        #copy_attrs = ['unit','dtypes']
        
        for attr, aliases in self._Element__aliases.items():
            alias = aliases[0]
            if hasattr(self, attr):
                value = getattr(self, attr)
                #if attr in copy_attrs:
                #    value = value.copy()
                d[alias] = value
        
        d.update(self.__kw)
        self.__dict = d
        
        if kw:
            d = dict(d, **kw)
        
        return d
    
    
    def update(self, d, normalize=True):
        resolve_attrs = ['unit']
        resolve_elements = ['dtypes','multi']
        found = []
        
        for attr, aliases in self._Element__aliases.items():
            for alias in aliases:
                if alias in d:
                    value = d[alias]
                    if attr in resolve_attrs:
                        value = _resolve(value)
                    if attr in resolve_elements:
                        if isinstance(value, dict):
                            value = {k: _resolve(v, 'try') for k,v in value.items()}
                        else:
                            value = [_resolve(v) for v in value]
                    setattr(self, attr, value)
                    found.append(alias)
        
        self.__kw = {k: v for k,v in d.items() if k not in found}
        
        if hasattr(self, '__dict'):
            del self.__dict
        
        if normalize:
            if hasattr(self, 'isnorm'):
                del self.isnorm
            normalize_element(self)
        else:
            self.to_dict()
    
    
    def get(self, key, *default):
        return self.__dict.get(key, *default)
    
    
    def __contains__(self, key):
        return key in self.__dict
    
    
    def __len__(self):
        ignore = {'_copy_','_isnorm_'}
        return sum(1 for x in self.__dict if x not in ignore)
    
    
    @classmethod
    def verify_params(cls, type, kw):
        must_contain_attr = '_{}__must_contain'.format(cls.__name__)
        if hasattr(cls, must_contain_attr):
            must_contain = getattr(cls, must_contain_attr)
            for attr in must_contain:
                aliases = cls._Element__aliases[attr]
                if not any(x in kw for x in aliases):
                    raise BadInstruction('Does not contain: {}'.format(attr))


class Container(Element):
    
    def __getitem__(self, key):
        if not isinstance(key, tuple):
            key = (key,)
        
        d = self.to_dict()
        unit = d.get('unit', {})
        
        if len(key) == 1:
            unit.update(_resolve(key[0], 'try'))
        elif len(key) > 1:
            resolved = [_resolve(k, 'try') for k in key]
            types_only, values_only, other = [], [], []
            for x in resolved:
                if len(x) == 1 and '_type_' in x:
                    if isinstance(x.get('_type_'), tuple):
                        types_only += list(x.get('_type_'))
                    else:
                        types_only.append(x.get('_type_'))
                elif len(x) == 1 and '_value_' in x:
                    values_only.append(x.get('_value_'))
                elif len(x) == 1 and '_multival_' in x:
                    values_only += list(x.get('_multival_'))
                else:
                    other.append(x)
            
            _type = {'_type_': tuple(types_only) if len(types_only) > 1 else types_only[0]} if len(types_only) else {}
            _value = ({'_multival_': values_only} if len(values_only)> 1 else {'_value_': values_only[0]}) if values_only else {}
            if _type and (not _value and not other):
                unit.update(_type)
            elif _value and (not _type and not other):
                unit.update(_value)
            else:
                multi = []
                if _type:
                    multi.append(_type)
                if _value:
                    multi.append(_value)
                if other:
                    multi += other
                unit['_multi_'] = multi
        
        if 'unit' in d or unit:
            d['unit'] = unit
        
        return Container(**d)
    
    
    def __iter__(self):
        raise TypeError("'Container' object is not iterable.")


class Multi(Element):
    def __init__(self, *elements, **kw):
        if not elements:
            raise BadInstruction('No elements provided')
        if 'multi' not in 'kw':
            kw['multi'] = elements
        super().__init__(**kw)


class Type(Element):
    __must_contain = ['type']
    
    def __init__(self, *type, **kw):
        if not type:
            raise BadInstruction('type not provided')
        if 'type' not in kw:
            kw['type'] = type
        super().__init__(**kw)


class Value(Element):
    __must_contain = ['value']
    
    def __init__(self, value, **kw):
        if 'value' not in kw:
            kw['value'] = value
        super().__init__(**kw)


class MultiVal(Element):
    __must_contain = ['multival']
    
    def __init__(self, *values, **kw):
        if 'multival' not in kw:
            kw['multival'] = list(values)
        super().__init__(**kw)


class Dtyct(Container):
    __must_contain = ['dtypes']
    
    def __init__(self, dtypes, **kw):
        if 'dtypes' not in kw:
            kw['dtypes'] = dtypes
        super().__init__(dict, **kw)
    
    @classmethod
    def from_dtypes(cls, *kw, **dtypes):
        kw = kw[0] if kw else {}
        return cls(dtypes, **kw)


class IntRange(Element):
    def __init__(self, range, **kw):
        if 'range' not in kw:
            kw['range'] = range
        super().__init__(int, **kw)


class FloatRange(Element):
    def __init__(self, range, **kw):
        if 'range' not in kw:
            kw['range'] = range
        super().__init__(float, **kw)


Str = Element(str)
Int = Element(int)
Float = Element(float)
Bool = Element(bool)
Null = Element(type(None))
List = Container(list)
Dict = Container(dict)
NullDict = Container(dict, unit={'_defval_': None}, default_dtype=None)
Set = Container(set)


__all__ = ['Str','Int','Float','Bool','Null','List','Dict','Dtyct','NullDict',
           'Set','Multi','Type','Value','MultiVal','Element','Container',
           'IntRange','FloatRange','normalize_element','normalize','init_data',
           'verify_data','convert_exception','fill_missing']
