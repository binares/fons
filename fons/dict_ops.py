import copy as _copy
from collections import namedtuple, OrderedDict


def nt_to_od(namedtuple_or_form, fill=None):
    nf = namedtuple_or_form
    od = OrderedDict()
    
    try:
        #test if any values assigned to nf
        nf[0]
    except TypeError:
        #nf was template/form
        od = OrderedDict(zip(nf._fields,[fill]*len(nf._fields)))
    else:
        for i,k in enumerate(nf._fields):
            od[k] = nf[i]

    return od


def od_to_nt(ordereddict, nt_classname=None, return_form=False):
    od = ordereddict

    fields = list(od.keys())
    values = list(od.values())

    if nt_classname is None:
        nt_classname = 'a_namedtuple'

    nt_form = namedtuple(nt_classname,fields)
    nt = nt_form(values)

    if return_form:
        return nt, nt_form
    
    return nt


def apply_until_get(objs, f, condition='is not None', **kw):
    if condition == 'is not None':
        condition = lambda x: x is not None
        
    i = 0
    for o in objs:
        v = f(o)
        if condition(v):
            return v
        i += 1
    
    if not i:
        raise ValueError('No objs provided')
    
    if 'return2' in kw:
        return kw['return2']
    else:
        return v


def deep_get(objs, keywords, condition='is not None', **kw):
    if isinstance(keywords,str): keywords = [keywords]
    notFound = object()
    return_first = (condition == 'first')
    if return_first:
        condition = lambda x: x is not notFound
    
    def recursive_get(obj, keywords=keywords):
        keywords = iter(keywords)
        k = next(keywords)
        if obj is None:
            return None if not return_first else notFound
        try: v = obj[k]
        except KeyError:
            return None if not return_first else notFound
        try: return recursive_get(v,keywords)
        except StopIteration:
            return v
        
    v = apply_until_get(objs,recursive_get,condition, **kw)
    if v is notFound:
        return None
    return v
        

def _matches_new_value(x, new_value):
    """x is a key of hierarchy"""
    if isinstance(x, type):
        if isinstance(new_value, x):
            return True
        
    elif new_value == x:
        return True
    
    return False
    
    
def _is_dominant(new_value, old_value, hierarchy):
    type_old = type(old_value)
    hierarchy_mathes = [x for x in hierarchy if _matches_new_value(x, new_value)]
    doms_map = {'any': False, 'all': False, 'none': True}
    subs_map = {'any': True, 'all': True, 'none': False}
    
    for m in hierarchy_mathes:
        item = hierarchy[m]
        subs = doms = ()
        if item is None:
            continue
        elif isinstance(item, dict):
            subs = item.get('subs')
            doms = item.get('doms')
        elif isinstance(item, str):
            doms = item
        else:
            doms = item
            
        for name,x,map in [('doms', doms, doms_map),
                           ('subs',subs, subs_map)]:
            if isinstance(x, str) and x in map:
                return map[x]
            elif isinstance(x, tuple):
                if issubclass(type_old, x):
                    return name == 'subs'
            else:
                raise ValueError({m: item})
            
    return True
    
    
def deep_update(obj, new, copy=False, hierarchy={}, **kw):
    if not isinstance(obj,dict) or not isinstance(new,dict):
        return new if not copy else _copy.deepcopy(new)
    
    _is_dom = kw.get('_is_dominant')
    if _is_dom is None:
        _is_dom = (lambda x,y,h: True) if not hierarchy else _is_dominant
        kw['_is_dominant'] = _is_dom
    
    new_doms = set(k for k,v in new.items() 
                    if k not in obj or _is_dom(v, obj[k], hierarchy))
    
    _old = obj
    if copy:
        must_copy = lambda obj_key: obj_key not in new or \
                                     obj_key not in new_doms
        #only deepcopy values that are not overwritten
        # later anyways
        obj = {k: (_copy.deepcopy(v) if must_copy(k) else v)
               for k,v in _old.items()}
    
    for kN,vN in new.items():
        if kN in new_doms:
            obj[kN] = deep_update(_old.get(kN), vN, copy, hierarchy, **kw)
        
        
    return obj
