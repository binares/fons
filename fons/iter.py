import numpy as np
import pandas as pd
import collections
import itertools

SETLIKE = (set,)
LISTLIKE = (list, tuple, np.ndarray, pd.Index, collections.deque)
LISTSETLIKE =  LISTLIKE + SETLIKE
DICTLIKE = (dict,)
CONTAINERLIKE = LISTLIKE + SETLIKE + DICTLIKE
_SAMPLES = [(x for x in []), {}.keys(), {}.values(), {}.items()]
# This is covered by _is_known_iterator test
#_SAMPLES2 = [iter([]), iter(tuple()), iter({}), iter({}.keys()), iter({}.values()), iter({}).items(),
#             iter(set()), iter(str()), iter(range(1,2)),
#             iter(enumerate([])), iter(pd.Index([])), iter(np.array([]))]
#Note:
#type(iter(np.array([]))).__name__ == 'iterator'
GENLIKE = tuple(map(type,_SAMPLES)) + (range, enumerate, zip, map, filter, itertools.chain)
LISTGEN = LISTLIKE + GENLIKE

_MAP_LISTLIKE = {tuple: tuple,
                 list: list,
                 pd.Index: pd.Index,
                 np.ndarray: lambda x: np.asarray(tuple(x)),
                 set: set}


def _normalize_args(include_types, ignore_types):
    ignore_types = tuple(ignore_types)
    
    if not isinstance(include_types, str):
        include_types = tuple(include_types)
        
    elif include_types not in ('all','iterable'):
        raise ValueError(include_types)
    
    return include_types, ignore_types


def _is_known_iterator(_type, x):
    try: 
        return _type.__name__.endswith('iterator') and hasattr(x,'__iter__')
    except TypeError:
        return False


def _is_iterable(x):
    try:
        #return hasattr(x, '__iter__') or hasattr(x, '__getitem__')
        # __getitem__ does not always make it iterable (if it doesn't start with 0 index) 
        iter(x)
    except TypeError:
        return False
    else:
        return True
    
    
def _tests(x, include_types, ignore_types, **kw):
    _type = type(x)
    
    if ignore_types and issubclass(_type, ignore_types):
        return False
    
    # returns self (e.g. next(iter('a')))
    if 'last' in kw and kw['last'] is x:
        return False
    
    # Just in case the "last" test failed on str (str id-s differ for some reason)
    if issubclass(_type, str) and len(x) < 2:
        return False
    
    if isinstance(include_types, str) and include_types in ('all','iterable'):
        return _is_iterable(x)
       
    if issubclass(_type, LISTSETLIKE):
        return True
    
    if issubclass(_type, GENLIKE) or _is_known_iterator(_type, x):
        return True
    
    if not isinstance(include_types, str) and include_types and issubclass(_type, include_types):
        return True
    
    return False
    

def flatten(x, include_types=(), ignore_types=(), astype=None, **kw):
    """
       Flattens a "known" iterable (NB! while yet ignoring strings, dicts, custom defined classes)
        flatten([2, (3,4,{5}), {6: 7}, '89', iter('10'), {11:12}.items()], astype=list) ->
            ->  [2, 3, 4, 5, {6: 7}, '89', '1', '0', 11, 12]
       `included_types` / `ignore_types` also applies to subclasses.
       If `x` itself is "ignored", raises TypeError: flatten(2), flatten('abc')
       Included by default: list, tuple, deque, set, np.ndarray, pd.Index, 
                            dict.keys, dict.values, dict.items, filter, map, generator,
                            any class which name ends with "iterator" and has "__iter__" attr
                            (for including types like list_iterator, resulting from iter([]))
       Are NOT included by default:
                            Custom defined classes with __iter__ / __getitem__,
                            pd.Series, pd.DataFrame, dict, str, namedtuple
                            (the reason for ignoring dict, pd.Series, pd.DataFrame is to avoid
                             accidentally dropping extra information (keys, index, columns))
       For including ANY iterable, pass `include_types="all", or use `fliter` function instead.
       
       Returns: itertools.chain object, or `astype(result)` if `astype` is specified.
    """
    r = kw.get('r',0)
    
    if not r:
        include_types, ignore_types = _normalize_args(include_types, ignore_types) 
    
    if not _tests(x, include_types, ignore_types, **kw):
        if r == 0:
            raise TypeError('Obj must be list(set)like or generator-like; Got: {}'.format(type(x)))
        return (x,)
    
    generators = (flatten(y, include_types, ignore_types, None, r=r+1, last=x) for y in x)
    flat = itertools.chain.from_iterable(generators)
    
    if astype is not None:
        astype = _MAP_LISTLIKE.get(astype, astype)
        flat = astype(flat)
    
    return flat


def flatten2(x, include_types=(), ignore_types=(), astype=None):
    """
    Ignores `set` subtypes
    """
    ignore_types = tuple(ignore_types) + (set,)
    
    return flatten(x, include_types, ignore_types, astype)


def flatten_dict(x, include_types=(), ignore_types=(), astype=None):
    """
    'Includes `dict` subtypes
    """
    if not isinstance(include_types, str):
        include_types = tuple(include_types) + (dict,)
        
    return flatten(x, include_types, ignore_types, astype)


def fliter(x, ignore_types=(), astype=None):
    """
    Flattens all iterable objects within (including strings!).
    """
    return flatten(x, 'all', ignore_types, astype)


def is_flat(x, include_types=(), ignore_types=()):

    include_types, ignore_types = _normalize_args(include_types, ignore_types) 
    
    if not _tests(x, include_types, ignore_types):
        raise TypeError('Obj must be list(set)like or generator-like; Got: {}'.format(type(x)))
    
    if any(_tests(y, include_types, ignore_types) for y in x):
        return False
    
    return True


def is_flit(x, ignore_types=()):
    return is_flat(x, 'all', ignore_types)


def unique(seq, key=None, op=None, astype=None):
    """
    :param seq: an iterable
    :param key: None / <function> / <str> / <object>
                if <str> (or <object>), `x[key]` is used, 
                 or `getattr(x, key)` if x does not possess __getitem__
    :param op: None / lambda x,y: x==y / '__eq__' / '=='
               function must return positive for match; if left to None then 
               `x in seen` is used, where `seen` is set (or list, if `x` is not hashable)
    :returns: iterator, or `astype(result)` if `astype` is specified.
    """

    keyfunc = key
    
    if key is not None and not hasattr(key,'__call__'):
        def keyfunc(x, key=key):
            if hasattr(x, '__getitem__'):
                return x[key]
            else:
                return getattr(x, key)
        
    if op is None:
        
        def is_first(x, seen_set=set(), seen_list=[]):
            try: hash(x)
            except TypeError:
                is_hashable = False
            else: is_hashable = True
            
            if is_hashable:
                if x not in seen_set:
                    seen_set.add(x)
                    return True
            else:
                if x not in seen_list:
                    seen_list.append(x)
                    return True
            
            return False
        
    else:
        op2 = op
        if isinstance(op, str):
            if op == '==':
                op2 = lambda y,x: y==x
            else:
                op2 = lambda y,x: getattr(y,op)(x)
        
        
        def compare(y, x, f=op2):
            v = f(y, x)
            if v is not NotImplemented:
                return v
            
            v = f(x, y)
    
            if v is NotImplemented:
                return False
            
            return v
        
        
        def is_first(x, seen_list=[]):
            if not any(compare(y,x) for y in seen_list):
                seen_list.append(x)
                return True
            
            return False
            
    
    if keyfunc is not None:
        def uniq(x, keyfunc=keyfunc):
            x2 = keyfunc(x)
            return is_first(x2)
    else:
        uniq = is_first


    seq_unique = filter(uniq, seq)
    
    if astype is not None:
        astype = _MAP_LISTLIKE.get(astype, astype)
        seq_unique = astype(seq_unique)
    
    return seq_unique



def consume(iterator, n=None):
    "Advance the iterator n-steps ahead. If n is None, consume entirely."
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(itertools.islice(iterator, n, n), None)
        
        
def sequence_insert(seq, ins_to, *, key=None, duplicates='keep', sort=False):
    """Inserts sequence items into `ins_to`. Items in both arrays must be sortable (by `key`),
        and both arrays must be sorted beforehand in ascending order.
       sequence_insert([{'a': 2},{'a': 5}], [{'a': 2, 'x': 15}, {'a': 4}],
                                    key=lambda x: x['a'], duplicates='drop') ->
           -> ins_to = [{'a': 2, 'x': 15}, {'a': 4}, {'a': 5}]
       
       :param duplicates: if 'drop', duplicates are dropped, where keep='last';
                          if 'keep', do [..., old_item, equal_new_item_here, ..]
       :param sort: if True, first sorts `seq` (not `ins_to`!)
       :returns: None"""
    if duplicates not in ('keep','drop'):
        raise ValueError(duplicates)
    if sort:
        seq = sorted(seq, key=key)
    
    drop = (duplicates=='drop')
    is_deque = isinstance(ins_to, collections.deque)
    key = (lambda x: x) if key is None else key
    
    for this in seq:
        compare_this = key(this)
        try:
            i, are_equals = next((-i,key(x)==compare_this) 
                                        for i,x in enumerate(reversed(ins_to)) 
                                    if compare_this>=key(x))
            if i == 0 and (not are_equals or not drop):
                i = None 
        except StopIteration:
            i, are_equals = (0, False)
            
        if are_equals and drop:
            ins_to[i-1] = this
        else:
            if i is None:
                ins_to.append(this)
            else:
                #[2,3,4].insert(-1,5) ->
                #[2,3,5,4]
                try:
                    ins_to.insert(i, this)
                except IndexError as e:
                    if is_deque:
                        ins_to.popleft()
                        ins_to.insert(i, this)
                    else:
                        raise e
                    
    return None

