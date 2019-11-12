import os
from collections import OrderedDict
import json
import functools
import warnings
import filelock
import yaml
import copy as _copy
import pytz
import datetime
from _hashlib import new
dt = datetime.datetime
td = datetime.timedelta

from fons.dict_ops import (deep_update, deep_get)
from fons.iter import unique
from fons.verify import init_data, normalize, _isnorm, verify_data
import fons.log as _log

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

_META_NORM = {
    '_type_':dict,
    'default_dtype': None,
    'dtypes': {
        'interval': float,
        '1st_only': {
            '_type_': list,
            'unit': {'_type_': str}},
        'null_overwrite': bool,
        'init': bool,
        'deep': bool,
        'borrow_keys': bool,
        'borrow_meta': bool,
        
        'counter': int,
        'config': str,
        'exclude': {
            '_type_': list,
            'unit': {'_type_': str}},
        'last_input': dict,
        'last_input_meta': dict,
        'last_modified': {
            '_type_': dict,
            'unit': {'_type_': float}},
    }
}

_CFG_DTYPES = {
    '__meta__': _META_NORM,
}
normalize(_META_NORM)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, dt):
            #return o.isoformat()
            #"values": [o.year,o.month,o.day,o.hour,o.minute,o.second,o.microsecond]}
            return {'_type_': 'dt',
                    'v': o.isoformat()}
             
        elif isinstance(o,td):
            return {'_type_': 'td',
                    'v': [o.days,o.seconds,o.microseconds]}
        
        else: return json.JSONEncoder.default(self, o)
        
        
class DateTimeEncoderNumeric(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, dt):
            #return o.isoformat()
            #"values": [o.year,o.month,o.day,o.hour,o.minute,o.second,o.microsecond]}
            if o.tzinfo is None:
                o = o.replace(tzinfo=pytz.utc)
                
            v = dt.timestamp(o) * 1000
            v = max(int(v), v)
                
            return {'_type_': 'dt',
                    'v': v}
             
        elif isinstance(o,td):
            v = o.total_seconds() * 1000
            v = max(int(v), v)

            return {'_type_': 'td',
                    'v': v}
        
        else: return json.JSONEncoder.default(self, o)
    
    
def _extract_literal(s):
    j1 = s.find("<")
    j2 = s.rfind(">")
    
    if j1 == 0 and j2 == len(s)-1:
        return json.loads(s[j1+1:j2].strip())
    
    return s
    
    
def _get_key_value(line):
    i1 = line.find("[")
    i2 = line.find("]")
    
    if i1 != 0 or i2 == -1:
        raise ValueError(line)
    
    key = line[i1+1:i2].strip()
    value = line[i2+1:].strip()

    key = _extract_literal(key)
    #value = json.loads(value)
      
    return key,value


def get_params(text, keys=[], sep='\n', ordered=False, **kw):
    """A custom json-like file format for dicts, which supports non-str keys.
       Example:
        [param_name] "json value"
        [<2>] null
        [<"<2>">] null
        //comment line 
         -> {"param_name": "json value", 2: None, "<2>": None}
      If param_name is surrouned with <>, it is assumed to be json value,
      otherwise it is interpreted as string."""
    lines0 = [x.strip() for x in text.split(sep)]

    D = dict() if not ordered else OrderedDict()
    
    return_nrs_n_lines = kw.get('return_nrs_n_lines')
    line_nrs = OrderedDict()
    init = kw.get('init')
    missing = kw.get('missing','raise')
    
    if keys is not None and len(keys):
        do_keys, unseen = True, set(keys)
    else: 
        do_keys = unseen = None
    
    for line_nr,line in enumerate(lines0):
        if not len(line) or line[:2] == '//':
            continue
        
        try:
            k,v = _get_key_value(line)
        except ValueError:
            warnings.warn('Damaged line ({line_nr}): "{line}"' \
                          .format(line_nr=line_nr, line=line))
            continue
        
        if do_keys:
            if k not in keys: continue
            try: unseen.remove(k)
            except KeyError: pass
        
        v_json = json.loads(v)
        D[k] = v_json if not init else init_data(v_json)
        line_nrs[k] = line_nr
        
    
    if do_keys and len(unseen) and missing=='raise':
        raise KeyError('Missing Keys: {}'.format(list(unseen)))
        
    if return_nrs_n_lines:
        return D, line_nrs, lines0
    
    return D


def read_params(path, keys=None, ordered=False, update=None, **kw):
    """Read params from file. 
       If `keys` is given, only those key-values are returned
       (if a key is missing then KeyError is raised)."""
    encoding = kw.get('encoding')
    if encoding is None: encoding = 'utf-8'
    
    with open(path,encoding=encoding) as f:
        text = f.read()
    
    item = get_params(text, keys=keys, ordered=ordered, **kw)
    
        
    if isinstance(update,dict):
        if kw.get('read_nrs_n_lines'):
            update.update(item[0])
        else: update.update(item)
    
    return item


def save_params(path, D, *, read_path=None, mode='a', **kw):
    """Save params to a file, while retaining file's previous params and comments.
       :param read_path: if given, previous params are read from that file
                         (instead of the file to be overwritten, if exists)
       :param mode: 'a' -> "append" new params to previous ones found in the file
                    'w' -> overwrite the file, disregarding its previous content"""
    line_nrs = {}
    lines = []
    
    cls = kw.get('cls')
    if cls is None: cls = DateTimeEncoder
    elif cls == 'DateTimeEncoder': cls = DateTimeEncoder
    elif cls == 'DateTimeEncoderNumeric': cls = DateTimeEncoderNumeric
    elif isinstance(cls,str):
        raise ValueError('Unknown cls: {}'.format(cls))
    
    deep = kw.get('deep')
    init = kw.get('init',True)
    read_path = path if read_path is None else read_path
    
    if os.path.isfile(read_path) and mode in ('a', None):
        #Note that `D2` and `line_nrs` contain only the requested keys (D.keys()) and their line nrs,
        # while `lines` contains all lines (in str format) in the file
        D2, line_nrs, lines = read_params(read_path, list(D.keys()), ordered=True,
                                          return_nrs_n_lines=True, init=init, missing='ignore')
        D2.update(D) if not deep else deep_update(D2,D)
        D = D2
    
    
    llen = len(lines)
    
    for k,v in D.items():
        if isinstance(k, str):
            k_final = k if not (k.startswith('<') and k.endswith('>')) else '<"{}">'.format(k)
        else:
            k_final = '<{}>'.format(k)
        
        line = '[{}] {}'.format(k_final, json.dumps(v,cls=cls))
        
        line_nr = line_nrs.get(k)
        
        if line_nr is not None:
            lines[line_nr] = line
        else:
            lines.append(line)
    
    if len(lines) > llen and lines[llen-1][:2] == '//':
        lines.insert(llen,'')
        
    if kw.get('comments'):
        lines += ['//'+c for c in kw['comments']]
    
    encoding = kw.get('encoding')
    if encoding is None:
        encoding = 'utf-8'
    
    write_txt = '\n'.join(lines)
    
    with open(path, 'w', encoding=encoding) as f:
        f.write(write_txt)


class SafeFileLock(filelock.FileLock):
    def __init__(self, filepath, timeout=-1, poll_interval=0.02, log=True):
        """NB! '.lock' will be added to filepath"""
        lock_file = filepath + '.lock'
        self._poll_interval_given = poll_interval
        self._log_given = log
        super().__init__(lock_file, timeout)
        
    def acquire(self, timeout=None, poll_interval=None, log=None):
        if poll_interval is None:
            poll_interval = self._poll_interval_given
        if log is None:
            log = self._log_given
        
        try: return super().acquire(timeout,poll_interval)
        except filelock.Timeout as e:
            if log: logger.error(e)
            class ReturnProxy(object):
                def __init__(self, lock):
                    self.lock = lock
                    return None
                def __enter__(self):
                    return self.lock
                def __exit__(self, exc_type, exc_value, traceback):
                    self.lock.release()
                    return None
            return ReturnProxy(lock = self)


def wait_filelock(filepath, timeout=0.2, poll_interval=0.02, log=False):
    with SafeFileLock(filepath,timeout,poll_interval,log):
        pass


#-------------------------------

def _get_force_update(paths, meta, counter, force_update):
    if not counter or force_update:
        return True
    
    lm = meta['last_modified']
    
    #if user decided to change the path of a file
    if any(p not in lm for p in paths):
        return True
        
    for path,time in lm.items():
        cur_last_modified = os.path.getmtime(path)
        if time != cur_last_modified:
            return True
    
    return False
    
    
def _load_settings(path, ftype, create, meta, force_update, return2):
    if ftype is None:
        loc = path.rfind('.')
        if loc != -1:
            ftype = path[loc+1:].lower()
    else: ftype = ftype.lower()
    
    if os.path.exists(path): pass
    elif create:
        with open(path,'w') as f:
            f.write('')
    else:
        raise FileNotFoundError(path)
    
    last_modified = os.path.getmtime(path)
    
    if not force_update:
        return return2
    
    meta['last_modified'][path] = last_modified
    
    if ftype in ('yaml','yml'):
        with open(path, encoding='utf-8') as f:
            new = yaml.safe_load(f) or {}
    elif ftype == 'json':
        with open(path, encoding='utf-8') as f:
            new = json.load(f) or {}
    else:
        new = read_params(path)
    #else: raise ValueError('Unknown ftype: {}'.format(ftype))
    
    return new


def _verify_is_dict(x, param, raise_errors):
    is_dict = isinstance(x, dict)
    
    if not is_dict:
        msg = '{param} must be dict; got: {type}'.format(param=param, type=type(x).__name__)
        _handle_error(TypeError(msg), False, None, msg, raise_errors=raise_errors)
    
    return is_dict


def _handle_error(e, log_as_exception, txt=None, txt2=None, raise_errors=False):
    if txt:
        logger2.error(txt)
    if raise_errors:
        raise e
    if txt2:
        logger2.error(txt)
    if log_as_exception:
        logger.exception(e)


def _get_param(meta, key, value):
    if value is None:
        value = meta.get(key)
    
    return value


def _get_exclude(meta, new, counter, exclude):
    if not counter:
        if exclude is None:
            exclude = new.get('__exclude__')
    else:
        if exclude is not None and exclude != meta.get('exclude'):
            warnings.warn("`exclude` can't be changed when counter > 0")
        exclude = meta.get('exclude')

    if exclude is None:
        exclude = []
            
    if not hasattr(exclude, '__getitem__'):
        raise TypeError('`exclude` must be listlike, got: {}'.format(type(exclude)))
        
    meta['exclude'] = exclude
    
    return exclude
    

def _get_config(meta, new, counter, config=None, default=None):
    if not counter:
        if default is None:
            default = new.get('__default__')
        meta['default'] = default
    else:
        if default is not None and default != meta.get('default'):
            warnings.warn("`default` can't be changed when counter > 0")
        default = meta.get('default')
        
    if not counter:
        if config is None:
            config = new.get('__config__')
        if config is None:
            config = default
        meta['config'] = config
    else:
        if config is not None and config != meta.get('config'):
            warnings.warn("`config` can't be changed when counter > 0")
        config = meta.get('config')
    
    return config, default


def _get_config_dict(new, config, main_path, _load_args, *vid_args):
    if config is None:
        config_dict = new
    elif config not in new:
        raise KeyError('config: "{}" is not defined'.format(config))
    else:
        config_dict = new[config]
        
    if isinstance(config_dict, str):
        path = path0 = config_dict
        ftype = None
        
        if '|' in path:
            path, ftype = path.split('|')
            
        if ':' not in path:
            if main_path is None:
                msg = ("Config '{}' path is relative but the main file's path "
                       "isn't specified; got: \"{}\"").format(config, path0)
                raise ValueError(msg)
            
            main_path_dir = os.path.dirname(os.path.realpath(main_path))
            relative_path = path.strip('/').strip('\\')
            path = os.path.join(main_path_dir, relative_path)
            
        config_dict = _load_settings(path, ftype, *_load_args)
        
    _verify_is_dict(config_dict, 'config:{}'.format(config), *vid_args)
    
    if config_dict is None:
        config_dict = {}
        
    return config_dict
    
    
def _get_meta(old, *args):
    meta = old.get('__meta__')
    if meta is None:
        old['__meta__'] = meta = {}

    if not _verify_is_dict(meta, '__meta__', *args):
        meta = {}
    
    for k,defval in [['counter',0],
                     ['last_modified',{}],
                     ['last_input',{}],
                     ['last_input_meta',{}]]:
        if meta.get(k) is None:
            meta[k] = defval
        
    return meta
        
        
def _update_meta(meta, config_dict, default_dict, logging_level, raise_errors):
    
    def _notify(k, v):
        logger2.log(logging_level, 'Setting __meta__ param "{}" to `{}`'.format(k,v))
        
    meta_default = default_dict.get('__meta__')
    meta_config = config_dict.get('__meta__')
        
    if meta_config is None or not _verify_is_dict(meta_config, 'meta_config', raise_errors):
        meta_config = {}
        
    if meta_default is None or not _verify_is_dict(meta_default, 'meta_default', raise_errors):
        meta_default = {}
    
    #`borrow_keys` and `borrow_meta` themselves are always "borrowed"
    borrow_keys = deep_get([meta_config, meta_default], 'borrow_keys')
    borrow_meta = deep_get([meta_config, meta_default], 'borrow_meta')
    if borrow_meta is None:
        borrow_meta = borrow_keys
    
    for k,v in [['borrow_keys', borrow_keys],
                ['borrow_meta', borrow_meta]]:
        if v != meta.get(v):
            _notify(k,v)
        meta[k] = v
            
    lim = meta['last_input_meta']
        
    meta_defvals = {'1st_only': [], 'null_overwrite': True,
                    'interval': 15, 'init': False, 'deep': None}
    
    def _update_value(k, *v):
        if not v:
            v = meta_config.get(k)
            if v is None and borrow_meta:
                v = meta_default.get(k)
        else:
            v = v[0]
            
        if k in lim and lim[k] == v:
            return
        
        lim[k] = _copy.deepcopy(v)
        
        if v is not None:
            norm = next(x[1] for x in _META_NORM['items'] if x[0]==k)
            try: 
                verify_data(v, norm, missing='ignore', extra='error') #??
            except Exception as e:
                logger2.error('__meta__ param "{}" incorrectly formatted.'.format(k))
                if raise_errors:
                    raise e
                logger2.error(e)
                #raise e
                v = None
                
        if v is None:
            v = meta_defvals.get(k)
        
        _notify(k,v)
        meta[k] = v
        

    for k in meta_defvals:
        _update_value(k)
        

def _update_keys(meta, old, config_dict, default_dict, counter, 
                 config, default, exclude, init, verify, v_params,
                 raise_errors):
    
    _handle = functools.partial(_handle_error, raise_errors=raise_errors)

    last_input = meta['last_input']
    first_only = meta['1st_only'], 
    null_overwrite = meta['null_overwrite']    
    borrow_keys = meta['borrow_keys']
    
    skip = ['__meta__'] + exclude
    if default is None:
        skip += ['__config__','__default__','__exclude__']
        if config is not None:
            skip += [config]
            
    if not borrow_keys:
        skip += [k for k in default_dict if k not in config_dict]

    all_keys = list(unique(list(config_dict.keys()) + list(default_dict.keys())))
    selected_keys = list(filter(lambda x: x not in skip, all_keys))
    
    if verify is not None and not _isnorm(verify):
        verify = normalize(verify)
        
    if v_params is None: v_params = {}
    v_params = dict({'missing': 'ignore', 'extra': 'error'}, **v_params) #??
    
    new_dict = {}
    exc = None
    
    for k in selected_keys:
        if counter and k in first_only:
            continue
        
        if k in config_dict or not borrow_keys:
            new_val = config_dict[k]
        else: 
            new_val = default_dict.get(k)

        if new_val is None and k in old and not null_overwrite: continue
        elif k in last_input and new_val == last_input[k]: continue
        
        last_input[k] = _copy.deepcopy(new_val)
        
        if init:
            try: new_val = init_data(new_val)
            except Exception as e:
                exc = e
                _handle(exc, True, 'Could not initiate param "{}"'.format(k))
                break
        
        if verify is not None:
            try: norm = next(x[1] for x in verify['items'] if x[0]==k)
            except StopIteration as e:
                exc = KeyError('Unknown param: {}'.format(k))
                _handle(exc, False, None, 'Unknown param: {}'.format(k))
                break

            try: verify_data(new_val, norm, **v_params)
            except Exception as e:
                exc = e
                _handle(exc, True, 'Param "{}" incorrectly formatted.'.format(k))
                break
            
        new_dict[k] = new_val
        
    return new_dict, exc
        

def update_settings(new, old=None, verify=None,*, ftype=None,
                    deep=None, init=False, logging_level='INFO',
                    create=False, v_params=None, force_update=False,
                    errors='raise', config=None, default=None, exclude=None):
    """Update a dict with new values.
       :param new: dict or path to a file (containing dict)
       :param old: previous dict, meant to be reused on all calls
       :param verify: the `norm` dict to be used to verify 
       :param create: if True and a file doesn't exist, create an empty one;
       '              otherwise raise FileNotFoundError
       :param errors: 'ignore', 'raise', 'log' ('ignore' is logged too)
    """
    if errors not in ('ignore','raise','log'):
        raise ValueError(errors)
    logging_level = _log._level_to_int(logging_level)
    raise_errors = (errors == 'raise')
    vid_args = (raise_errors,)
        
    if old is None:
        old = {}
    
    meta = _get_meta(old, *vid_args)
    counter = meta['counter']
    path = new if isinstance(new, str) else None
    
    force_update = _get_force_update([path], meta, counter, force_update)

    if path is not None:
        new = _load_settings(path, ftype, create, meta, force_update, old)
        if new is old:
            return old
    
    config, default = _get_config(meta, new, counter, config, default)
    #print(config, default)
    exclude = _get_exclude(meta, new, counter, exclude)

    meta['counter'] += 1
    
    _load_args = (create, meta, True, {})
    config_dict = _get_config_dict(new, config, path, _load_args, *vid_args)
    
    if config == default:
        default_dict = config_dict
    else:
        default_dict = _get_config_dict(new, default, path, _load_args, *vid_args)

    _update_meta(meta, config_dict, default_dict, logging_level, raise_errors)
    
    init = _get_param(meta, 'init', init)
    deep = _get_param(meta, 'deep', deep)
    
    new_dict, exc = _update_keys(meta, old, config_dict, default_dict, counter,
                                 config, default, exclude, init, verify, v_params,
                                 raise_errors)
    
    #We do not want to update only half the params (might cause a fiasco)
    # either update all or reject and return the old
    if exc is not None:
        return old
    
    for k,new_val in new_dict.items():
        logger2.log(logging_level, 'Setting param "{}" to `{}`'.format(k, new_val))
    
    if deep:
        deep_update(old, new_dict)
    else:
        old.update(new_dict)
    
    return old

