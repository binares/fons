DEFAULT_REGISTRY = set()


def create_name(name=None, default=None, registry=None, add_int='always'):
    if registry is None:
        registry = DEFAULT_REGISTRY
    
    if isinstance(name,str):
        new_name =  name
        
    elif isinstance(name,int):
        new_name = '{}-{}'.format(default, name) if default is not None else str(name)
    
    elif name is None and add_int == 'if_taken' and \
            default is not None and default not in registry:
        new_name = default
        
    elif name is None:
        i = 1
        while True:
            new_name = '{}-{}'.format(default, i) if default is not None else str(i)
            if new_name not in registry:
                break
            i+=1
            
    else: 
        raise TypeError(type(name))
    
    
    registry.add(new_name)
    
    return new_name
