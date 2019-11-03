import math
import datetime
dt = datetime.datetime
td = datetime.timedelta

from fons.nan import nan


class QuitException(Exception):
    """Raised to terminate an obj
       Conventions:
         Obj is assumed to catch it internally.
         If obj's function was in the process 
          of returning something, then will return the 
          args[0] instead (if present)."""
        
    _level = 0


class WaitException(Exception):
    def __init__(self,*args,**kw):
        self.time_initiated = dt.utcnow()
        
        time = kw.get('time',0)
        if 'time' in kw: pass
        elif not len(args): pass
        elif isinstance(args[0], bool): pass
        elif isinstance(args[0], (int,float,td)):
            time = args[0]
            args = args[1:]
        
        if isinstance(time,td):
            time /= td(seconds=1)
        elif not isinstance(time, (int,float)):
            raise TypeError(type(time))
        
        msg = kw.get('msg')
        if msg is None:
            msg =  'Wait time of {} seconds is needed'.format(math.ceil(time))
        
        self.args = (msg,) + tuple(args)
        self.wait_time = time

    def get_time_remaining(self):
        return self.wait_time - (dt.utcnow() - self.time_initiated) / td(seconds=1)
    
    _level = 0
    wait_time = 0
    time_initiated = dt.utcfromtimestamp(0)


class TerminatedException(Exception):
    _level = 0
    

#-------------------------------

class BaseVeriError(Exception):
    pass

class InitError(BaseVeriError):
    pass
    
class BadInstruction(BaseVeriError):
    pass


class VeriError(BaseVeriError):
    def __init__(self, trace=[], got=nan, expected=nan, *args):
        if trace is not None:
            self.trace = trace
        else:
            self.trace = []
        
        self.level = max(0, len(self.trace) - 1)
        
        self.got = got 
        self.expected = expected
        
        self.craft_msg()
        
    
    def craft_msg(self):
        msg= '{}; '.format(''.join(self.trace))

        parts = []
        if self.got is not nan:
            parts.append('{}{}'.format(self._gotstr, repr(self.got)))
        if self.expected is not nan:
            parts.append('{}{}'.format(self._expstr, repr(self.expected)))
        eg = ", ".join(parts)
        
        msg = (msg + eg).strip()
        
        self.msg = msg #'{}; Got:{}, Expected:{}'.format("".join(self.trace), repr(got), repr(expected))
        #self._strmsg = '{}({})'.format(self.__class__.__name__, msg)
        
        #self.args = (self.msg,)
        
        
    def is_faulty(self, subset=None):
        return True
        
        
    def __str__(self):
        #return self._strmsg
        return '{}({})'.format(self.__class__.__name__, self.msg)
    
    """def __repr__(self):
        return self._reprmsg"""
        
    _gotstr = 'Got:'
    _expstr = 'Expected:'
    type = 'general'

    #__slots__ = ['trace','got','expected','level','msg','_strmsg'] #doesn't do anything, new attributes can still be added


class VeriTypeError(VeriError):
    type = 'type'

class VeriValueError(VeriError):
    type = 'value'
    

class VeriWithSubsetsError(VeriError):
    def is_faulty(self, subset=None):
        """is_missing = self.expected is not nan
        is_extra = self.got is not nan"""
        
        if subset is None:
            return {k1: (getattr(self,k0) is not nan) for k0,k1 in self.subsets}
        
        
        gen = (getattr(self,ss[0]) is not nan 
                for ss in self.subsets
               if ss[1] == subset)
        
        return any(gen)
    
    
    type = 'general'
    subsets = [('got','extra'),('expected','missing')]
    _gotstr = 'Extra:'
    _expstr = 'Missing:'
    


class VeriKeyError(VeriWithSubsetsError):   
    type = 'key'

class VeriIndexError(VeriWithSubsetsError):
    type = 'index'
    _gotstr = 'Size mismatch:'


#------------------------------

class TickerException(Exception):
    pass


class TickerAlreadyAdded(TickerException):
    pass


class TickerWaitException(TickerException, WaitException):
    pass


class TickerTerminated(TickerException, TerminatedException):
    pass


class TickerQuitException(TickerException, QuitException):
    pass


class AllTerminated(TickerException):
    pass

#-----------------------------------------------

class ThreadEndException(Exception):
    pass

#-----------------------------------------------

class BreakException(Exception):
    pass

#----------------------------------------------

class ServerError(Exception):
    def __init__(self,msg):
        self.msg = msg
