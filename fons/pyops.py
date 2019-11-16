import pandas as pd
import numpy as np
import copy as _copy

TYPES = ('type','function','module')
_TYPES = tuple([cls for cls in object.__subclasses__() if cls.__name__ in TYPES])
IMMUTABLES = (int, float, str, bool, tuple, type(None))
COPY_METHOD = (pd.DataFrame, pd.Series, pd.DatetimeIndex, pd.Index, np.ndarray)

OPS = {
    '==': lambda x,y: x==y,
    '!=': lambda x,y: x!=y,
    '>': lambda x,y: x>y,
    '>=': lambda x,y: x>=y,
    '<=': lambda x,y: x<=y,
    '<': lambda x,y: x<y,
    'in': lambda x,y: x in y,
    'not in': lambda x,y: x not in y,
    'is': lambda x,y: x is y,
    'is not': lambda x,y: x is not y,
}


def update_obj(obj, new):
    istuple = isinstance(obj,tuple)
    LT = (list,tuple)
    tO,tN = type(obj),type(new)
    
    if isinstance(obj,LT) and isinstance(new,LT):
        lnO,lnN = len(obj), len(new)
        
        #using < vN is '_keep_' > will sometimes evaluate False, specifically when '_keep_' originates from init_data('_keep_')
        if istuple or tO is not tN:
            return tN([obj[i] if compare(vN,'_keep_') else (vN if i >= lnO else update_obj(obj[i],vN)) for i,vN in enumerate(new)])
        
        if lnO < lnN: obj.extend(new[lnO:])
        elif lnO > lnN: del obj[lnN:]
        
        for i,itm in enumerate(zip(obj,new)):
            vO,vN = itm
            if compare(vN,'_keep_'): continue
            elif vO is vN: continue #compare(vO,vN): continue
            else: obj[i] = update_obj(vO,vN)
            
        return obj
            
    
    elif isinstance(obj,dict) and isinstance(new,dict):
        for kN,vN in new.items():
            obj[kN] = update_obj(obj.get(kN),vN)
            
        return obj
        
        
    return new


#---------------------------------------

def exec_op(x, y, op="=="):
    function = OPS.get(op)
    
    if function is None:
        if not isinstance(op, str):
            raise TypeError('Operation is of unknown type: {}'.format(type(op)))
        else:
            raise ValueError('Unknown operation: {}'.format(op))

    return function(x, y)


def compare(x, norm, type_op='isinstance'):
    
    if x is norm:
        return True
    
    if type_op == 'isinstance' and not isinstance(x, type(norm)):
        return False
    
    elif type_op == 'is' and type(x) is not type(norm):
        return False
    
    elif hasattr(norm,'__name__'):
        if not hasattr(norm,'__name__'):
            return False
        elif x.__name__ != norm.__name__:
            return False
    
    
    try: iter(x)
    except TypeError: isiter = False
    else: isiter = not isinstance(x,str)
    
    
    if isinstance(x, (pd.DataFrame, pd.Series, pd.Index, np.ndarray)):
        try:
            answ = (x == norm)
        except ValueError:
            #different labels
            return False
        
        while not isinstance(answ,np.bool_):
            #must use np.bool_ (not bool, or np.bool)!
            answ = answ.all()
        
        if not answ:
            return False
    
    
    elif isinstance(x, dict):
        """try: _verify_keys(k.keys(),norm.keys())
        except KeyError: return False"""
        if x.keys() != norm.keys():
            return False
        
        for k,v in x.items():
            if not compare(v, norm[k], type_op=type_op):
                return False
          
          
    elif hasattr(norm,'__dict__'):
        if not hasattr(x,'__dict__'):
            return False
        elif not compare(x.__dict__, norm.__dict__, type_op=type_op):
            return False
        
    
    elif isinstance(x, set):
        if x != norm:
            return False
            
            
    elif isiter:
        if hasattr(x,'__len__') and hasattr(norm, '__len__'):
            if len(x) != len(norm):
                return False
            
        it_x = iter(x)
        it_norm = iter(norm)
        
        while True:
            exhausted = 0
            
            try: ix = next(it_x)
            except StopIteration:
                exhausted += 1
                
            try: inorm = next(it_norm)
            except StopIteration:
                exhausted += 1

            if exhausted == 1:
                return False
            elif exhausted == 2:
                break
            
            if not compare(ix, inorm, type_op=type_op):
                return False

                
    elif pd.isnull(norm):
        if not(pd.isnull(x)):
            return False
    
        
    elif x != norm:
        return False
    
    
    return True


#To avoid copy.deepcopy() if possible (faster)
def copy(obj):
    _type = type(obj)
    _name = _type.__name__
    
    #copy.deepcopy:
    # -doesn't work on modules
    # -functions are not copied (id remains same)
    # -classes are not copied
    # -instance's metadata may be lost (e.g copy.deepcopy(df), also df.copy() )
    # -built-in immutable instances seem to be not copied
    
    if _name in TYPES:
        return obj
    
    #user may define '__hash__' = None, but object in fact IS mutable;
    #therefore it is better to rely on known types to be immutable
    elif any(issubclass(_type,im) for im in IMMUTABLES):
        return obj
        
    elif any(issubclass(_type,cm) for cm in COPY_METHOD):
        return obj.copy()
    

    return _copy.deepcopy(obj)
