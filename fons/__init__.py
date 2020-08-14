__version__ = '0.2.1'
__author__ = 'binares'

'''
    Python library for various purposes.
    
    `fons` - latin for "source"
    
    Some useful functions and classes:
        * aio.call_via_loop_afut - call a (async)function via (another) loop (possibly running in a different thread),
                                    returns async future with pending result/exception thrown of the function
        
        * argv.parse_argv - for parsing input sys.argv into dict values and list values, modifying them, and de-parsing
        
        * func.(async_)limitcalls - a decorator for setting rate limit to (async) function/method
                                    @limitcalls(1, 5, action='sleep')
                                    def f(): pass     -> f can only be called once per every 5 seconds, sleeps until that delay is reached
        
        * io.update_settings - load dict from settings file, supporting multiple configs in the same or different files
        
        * iter.flatten - "flatten" a nested list (iterator): list(flatten([2,{3:4},[5,6,(7,)],'89'])) -> [2,{3:4},5,6,7,'89']
                          (by default includes only "known" iterators; doesn't include: dicts, strings, namedtuples, custom defined classes)
                            
        * iter.fliter - "flatten" any iterable: list(fliter([2,{3:4},[5,6,(7,)],'89'])) -> [2,3,4,5,6,7,'8','9']
        
        * iter.unique - keep each value of iterator only once: list(unique([2,3,2])) -> [2,3]
        
        * sched.(Async)Ticker.loop - repeatedly execute a (async)function with a set interval (supports pandas offsets, e.g. '1B')
        
        * time.dt_round - round datetime: dt_round(datetime.datetime(2016,3,1,2), 'D') -> datetime.datetime(2016,3,1)
        
        * verify.verify_data - assert the correctness of input data (useful for avoiding accidental user config mistypes)
'''
