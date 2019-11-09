from collections import defaultdict
import itertools
import copy as _copy

from fons.iter import unique


class Argv:
    def __init__(self, argv, apply={}):
        self.argv, self.map, self.non_mapped, self.indexes = \
                                            self.parse(argv)
        self.apply(apply, True)
    
    
    @staticmethod
    def parse(argv):
        new_argv = []
        map = {}
        non_mapped = []
        indexes = defaultdict(list)
        i = 0
        argv = tuple(argv)
        ln_argv = len(argv)
        var_count = 0
        _null = object()
        
        while i < ln_argv:
            x = argv[i]
            value = _null
            is_unique = True
            add_i = 0
            
            if x.startswith('-'):
                var = x[1:]
                try: value = argv[i+1]
                except IndexError:
                    raise ValueError('Incorrectly formatted argv: {}'.format(argv))
                add_i = 1
            elif '=' in x:
                j = x.find('=')
                var, value = x[:j], x[j+1:]
            else:
                var = x
            
            if value is not _null:
                is_unique = var not in map
                map[var] = value
            else:
                non_mapped.append(x)
            
            is_key = value is not _null
            add_to_argv = '{}={}'.format(var, value) if is_key else var
            
            if not is_unique:
                raise ValueError('Contains duplicate keyword: {}'.format(var))
            
            indexes[var].append((var_count, is_key))
            var_count += 1
            new_argv.append(add_to_argv)
            #else:
            #    _argv[indexes[var][0]] = add_to_argv
            i += (1 + add_i)
            
             
        return new_argv, map, non_mapped, indexes
    
    
    def contains(self, *vars, set=None):
        _sets = {None: (self.map, self.non_mapped),
                'mapped': (self.map,),
                'map': (self.map,),
                'non_mapped': (self.non_mapped,),
                'non-mapped': (self.non_mapped,),
                'nonmapped': (self.non_mapped,),}
            
        try: sets = _sets[set]
        except KeyError:
            raise ValueError(set)
        
        return any(any(x in _set for _set in sets) for x in vars)
    
    
    def which(self, vars, default=None, *, set=None):
        return next((x for x in vars if self.contains(x, set=set)), default)
    
    
    def apply(self, f_map, inplace=True):
        new_map = self.map.copy() if not inplace else self.map
        
        for k,f in f_map.items():
            if k in new_map:
                new_map[k] = f(new_map[k])

        return new_map
    
    
    def add(self, var, *value, index=None):
        _ln = len(value)
        argv, map, non_mapped, indexes = self._fetch_attrs()
        
        if _ln > 2:
            raise ValueError(value)
        
        is_key = (_ln == 1)
        
        if is_key:
            if var in map:
                if index is None:
                    index = next(x[0] for x in self.indexes[var] if x[1])
                self.drop(var, set='mapped')
            map[var] = value[0]
            txt = '{}={}'.format(var, value[0])
        else:
            non_mapped.append(var)
            txt = var
        
        ln_argv = len(argv)
        
        if index is None:
            index = ln_argv
        else:
            index = self._resolve_positions((index,), ln_argv, type='insert')[0]

        argv.insert(index, txt)
            
        self._readjust_indexes(var, indexes, ((index, is_key),), 'add')
            
        
    def drop(self, var, *, set=None, position=None):
        argv, map, non_mapped, indexes = self._fetch_attrs()
        is_both = set is None
        is_map = set in ('map','mapped')
        is_nonmapped = set in ('non_mapped','non-mapped','nonmapped')

        if not self.contains(var, set=set):
            return
        
        eligible = [x for x in indexes[var]
                    if x[1] and not is_nonmapped or not x[1] and not is_map]
        
        s = sorted(eligible, key=lambda x: x[0])
        
        if isinstance(position, int):
            position = (position,)
            
        if position is not None:
            position = self._resolve_positions(position, len(s), type='resolve')
            s = [s[j] for j in position]
        
        s = sorted(s, reverse=True, key=lambda x: x[0])
        
        for i, is_key in s:
            argv.pop(i)
            if is_key:
                del map[var]
            else:
                non_mapped.remove(var)
        
        self._readjust_indexes(var, indexes, s, 'drop')
    
    
    def drop_key(self, var):
        return self.drop(var, set='key')
    
    
    def drop_value(self, var):
        return self.drop(self, var, set='value')
                         
                
    @staticmethod
    def _readjust_indexes(var, indexes, changed, action='add'):
        if action not in ('add','drop'):
            raise ValueError(action)
        is_drop = (action=='drop')
        diff = -1 if is_drop else 1
        
        if is_drop and var in indexes:
            indexes[var] = [x for x in indexes[var] 
                            if not any(y[0]==x[0] for y in changed)]
            if not len(indexes[var]):
                del indexes[var]
        
        for c,is_key in sorted(changed, reverse=True, key=lambda x: x[0]):
            
            for inds in list(indexes.values()):
                for j in range(len(inds)):
                    index,_is_key = inds[j]
                    if index >= c:
                        inds[j] = (index+diff, _is_key)
                        
            if not is_drop:
                indexes[var].append((c, is_key))
             
        return indexes
    
    
    @staticmethod
    def _resolve_positions(positions, length, type='resolve'):
        if type not in ('resolve','insert'):
            raise ValueError(type)
        is_drop = (type=='resolve')
        diff = 0 if type=='resolve' else -1
        resolved = []
        
        for index in positions:
            if index > length:
                if is_drop: continue
                else: index = length
            elif index < 0:
                if index < -length and is_drop:
                    continue
                index = max(0, (length+diff)+index)
            resolved.append(index)
        
        return tuple(unique(resolved))
    
        
    def _fetch_attrs(self, copy=False):
        argv = self.argv[:] if copy else self.argv
        map = self.map.copy() if copy else self.map
        non_mapped = self.non_mapped[:] if copy else self.non_mapped
        indexes = _copy.deepcopy(self.indexes) if copy else self.indexes
        
        return argv, map, non_mapped, indexes
    
    
    def copy(self):
        attr_values = self._fetch_attrs(True)
        new = Argv([])
        for a,v in zip(('argv','map','non_mapped','indexes'), attr_values):
            setattr(new, a, v)
            
        return new
    
        
    def __getitem__(self, key):
        return self.map[key]
    
    def __iter__(self):
        return itertools.chain(self.mapped, self.non_mapped)
    
    def __contains__(self, key):
        return self.contains(key)
    
        
    @property
    def get(self):
        return self.map.get
    
    @property
    def mapped(self):
        return self.map
    

def parse_argv(argv, apply={}):
    return Argv(argv, apply)
