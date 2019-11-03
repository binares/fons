import asyncio
import time
import functools
import queue as _queue
from collections import defaultdict, namedtuple, Counter

import fons.log as _log
from fons.reg import create_name

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)

_STATION_NAMES = set()
_TRANSMITTER_NAMES = set()
_empty = object()
_qeitem = namedtuple('qe', 'queue event')


class Transmitter:
    def __init__(self, name=None):
        self._receptors = []
        #self._loops = Counter()
        self.name = create_name(name, self.__class__.__name__, _TRANSMITTER_NAMES)
        

    #def get_loops(self):
    #    return [loop for loop, count in self._loops.items() if count]
    
    
    def __iadd__(self, receptor):
        self.prepare(receptor)
        self._receptors.append(receptor)
        #loop = getattr(receptor,'_loop',None)
        #if isinstance(loop, asyncio.BaseEventLoop):
        #    self._loops[loop] += 1
        return self


    def __isub__(self, receptor):
        self._receptors.remove(receptor)
        #loop = getattr(receptor,'_loop',None)
        #if isinstance(loop, asyncio.BaseEventLoop):
        #    self._loops[loop] -= 1
        return self
    
    
    def prepare(self, receptor):
        pass
    

    def fire(self, *args, **kw):
        raise NotImplementedError
    
    
    @staticmethod
    def fire_loop_partials(loop_partials):
        for loop, partials in loop_partials.items():
            Transmitter._call_loop(loop, partials)
    
    @staticmethod
    def _call_loop(loop, partials):
        f = functools.partial(Transmitter._call_all, partials)
        if loop is None:
            f()
        elif loop.is_running():
            loop.call_soon_threadsafe(f)
        #If loop is not running then thread safety doesn't matter, right?
        # (or unless multiple threads are accessing the queue simultaneously?)
        else:
            f()
            
    @staticmethod
    def _call_all(partials):
        for f in partials:
            f()


class EventTransmitter(Transmitter):
    """Contains events"""
    
    def fire(self, *, op='set', **kw):
        """set/clear all events"""
        if not isinstance(op, str):
            op = 'set' if bool(op) else 'clear'
        loop_partials = defaultdict(list)
                    
        for event in self._receptors:            
            loop = event._loop if isinstance(event, asyncio.Event) else None
            loop_partials[loop].append(getattr(event, op))
        
        if kw.get('return_partials'):
            return loop_partials
        
        self.fire_loop_partials(loop_partials)


class QueueTransmitter(Transmitter):
    """Contains queues"""
    
    def prepare(self, receptor):
        receptor.messages_undelivered = 0
        receptor.messages_behind = 0
        
        
    def fire(self, item, *args, **kw):
        """put an item to all queues"""
        loop_partials = defaultdict(list)
        for queue in self._receptors:
            loop = queue._loop if isinstance(queue, asyncio.Queue) else None
            p = functools.partial(self._put_to_queue, queue, item)
            loop_partials[loop].append(p)
        
        if kw.get('return_partials'):
            return loop_partials
        
        self.fire_loop_partials(loop_partials)  
                
                
    def _put_to_queue(self, q, r):
        nr_forced = force_put(q, r)
        if nr_forced:
            qname = getattr(q,'name','')
            qnstr = " '{}'".format(qname) if qname else ''
            if getattr(q,'warn',True):
                logger2.warn('{} - had to discard {} item(s) in queue{}'\
                             .format(self.name, nr_forced, qnstr))
            q.messages_undelivered += nr_forced
        else:
            q.messages_behind += 1
            
    
class Station:
    def __init__(self, data=[], default_queue_size=0, 
                 default_queue_cls=asyncio.Queue, 
                 default_event_cls=asyncio.Event, *, 
                 name=None, loops=[]):
        self.storage = {}
        self.qtransmitters = {}
        self.etransmitters = {}
        self.channels = set()
        #maxsize 0 is infinite
        self.default_queue_size = default_queue_size
        self.default_queue_cls = default_queue_cls
        self.default_event_cls = default_event_cls
        self.channel_default_queue_sizes = {}
        self.name = create_name(name, self.__class__.__name__, _STATION_NAMES)
        #default loop for adding new queue/event
        #if left to None, add will use .get_event_loop()
        self._current_loop_id = 0
        self.loops = {}
        if isinstance(loops, dict):
            for loop_id,loop in loops.items():
                self.add_loop(loop,loop_id)
        else:
            for loop in loops:
                self.add_loop(loop)

        for item in data:
            if item['channel'] not in self.channels:
                self.add_channel(item['channel'], item.get('default_queue_size'))
            item2 = {x:y for x,y in item.items() if x not in ('default_queue_size',)}
            #if
            if 'id' in item2:
                self.add(**item2)
        
        
    def add_channel(self, channel, default_queue_size=None):
        if channel in self.channels:
            raise ValueError('Channel {} already added'.format(channel))
        self.channels.add(channel)
        self.qtransmitters[channel] = QueueTransmitter(self.name+'[QT]')
        self.etransmitters[channel] = EventTransmitter(self.name+'[ET]')
        self.storage[channel] = defaultdict(dict)
        self.channel_default_queue_sizes[channel] = default_queue_size
        
        
    def add_loop(self, loop=None, id=None):
        if id is None:
            id = self._current_loop_id
        if loop is None:
            loop = asyncio.get_event_loop()
            
        if id in self.loops:
            raise ValueError('Already taken id: {}'.format(id))
        """elif loop in self.loops.values():
            raise ValueError('Already existing loop: {}'.format(loop))"""
        
        self.loops[id] = loop
        
        if isinstance(id,int):
            self._current_loop_id = max(self._current_loop_id, id + 1)
        return id
    
    
    def add(self, channel, id=None, queue=None, event=None, maxsize=None, loops=None):
        if maxsize is None: 
            maxsize = self.channel_default_queue_sizes[channel]
        if maxsize is None: 
            maxsize = self.default_queue_size 
        
        if queue is not None and event is not None and isinstance(queue, asyncio.Queue) and \
            isinstance(event, asyncio.Event) and queue._loop is not event._loop:
                raise ValueError("Queue's loop doesn't match with event's loop")
            
        if loops is None:
            if queue is not None and isinstance(queue, asyncio.Queue):
                loops = [queue._loop]
            elif event is not None and isinstance(event, asyncio.Event):
                loops = [event._loop]
        loop_ids = self.get_loop_ids(loops, add=True)
        #if id is None:
        #    id = getattr(queue,'id',None)
        if id is None:
            id = self._create_id(channel, loop_ids)
            
        items = {}
        for loop_id in loop_ids:
            loop = self.loops[loop_id]
            _queue,_event = queue,event
            
            if queue is False: _queue = None
            elif queue is None:
                kw = {'loop': loop} if self.default_queue_cls is asyncio.Queue else {}
                _queue = self.default_queue_cls(maxsize, **kw)
            elif isinstance(queue, asyncio.Queue) and queue._loop is not loop:
                raise ValueError("Loop <{}> doesn't match with provided queue's loop".format(loop_id))
            
            if event is False: _event = None
            elif event is None:
                kw = {'loop': loop} if self.default_event_cls is asyncio.Event else {}
                _event = self.default_event_cls(**kw)        
            elif isinstance(event, asyncio.Event) and event._loop is not loop:
                raise ValueError("Loop <{}> doesn't match with provided event's loop".format(loop_id))
            
            if _queue is None and _event is None:
                continue
            
            new = _qeitem(_queue, _event)
    
            if id in self.storage[channel].get(loop_id, {}):
                raise ValueError('Id "{}" has already been added to channel "{}"'.format(id, channel))
            
            if _queue is not None:
                _queue.id = id
                self.qtransmitters[channel] += _queue
            if _event is not None:
                _event.id = id
                self.etransmitters[channel] += _event
                
            self.storage[channel][loop_id][id] = new
            items[loop_id] = new
            
        return items
        
        
    def add_queue(self, channel, id=None, queue=None, maxsize=None, loops=None):
        items = self.add(channel,id,queue,False,maxsize,loops=loops)
        return {loop_id: x.queue for loop_id, x in items.items()}
    
    
    def add_event(self, channel, id=None, event=None, loops=None):
        items = self.add(channel,id,False,event,loops=loops)
        return {loop_id: x.event for loop_id, x in items.items()}
    
    
    def remove(self, channel, id, loops=None):
        loop_ids = self.get_loop_ids(loops)
        
        for loop_id in loop_ids:
            try: item = self.storage[loop_id].pop(id)
            except KeyError: continue
            if item.queue is not None:
                self.qtransmitters[channel] -= item.queue
            if item.event is not None:
                self.etransmitters[channel] -= item.event
    
    
    def broadcast(self, channel, *put, op='set'):
        if len(put) > 1:
            raise ValueError(put)
        if len(put):
            item = put[0]
            self.qtransmitters[channel].fire(item)
        self.etransmitters[channel].fire(op=op)
        
        
    def broadcast_multiple(self, instr):
        """Ensures that multiple channel instructions with a shared loop 
            are fired strictly sequentially (no breaks between).
           :param instr: [{'_': channel, 'put': x, 'op': 'set'}, ...]
                         keywords "put" and "op" are optional"""
        loop_partials = defaultdict(list)
        
        for d in instr:
            if 'channel' in d:
                channel = d['channel']
            elif '_' in d:
                channel = d['_']
            else:
                raise KeyError('Missing keyword "channel" or "_"; got: {}'.format(d))
            
            qt_loop_partials = et_loop_partials = {}
            
            if 'put' in d:
                item = d['put']
                qt_loop_partials = self.qtransmitters[channel].fire(item, return_partials=True)
                
            if 'op' in d:
                op = d['op']
                et_loop_partials = self.etransmitters[channel].fire(op=op, return_partials=True)
                
            for x_loop_partials in (qt_loop_partials, et_loop_partials):
                for loop, partials in x_loop_partials.items():
                    loop_partials[loop] += partials
                    
        Transmitter.fire_loop_partials(loop_partials)
        
        
    def get(self, channel, loop=None, ids=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        loop_id = self.get_loop_ids([loop])[0]
        items = self.storage[channel][loop_id]
        
        if ids is None:
            return items
        elif hasattr(ids,'__iter__') and not isinstance(ids, str):
            return [items[id] for id in ids]
        else:
            return items[ids]
        
        
    def get_queue(self, channel, id, loop=None):
        return self.get(channel, loop, id).queue
    
    
    def get_event(self, channel, id, loop=None):
        return self.get(channel, loop, id).event
    
    
    def get_loop_ids(self, items=None, add=False):
        """Items: keys and/or loops"""
        if items is None: 
            return list(self.loops.keys())
        
        ids = []
        for x in items:
            if isinstance(x, asyncio.BaseEventLoop):
                try: id = next(id for id,loop in self.loops.items() if loop is x)
                except StopIteration:
                    if not add:
                        raise ValueError('Not existing loop: {}'.format(x))
                    id = self.add_loop(loop)
            elif x in self.loops:
                id = x
            else:
                raise ValueError('Not existing id: {}'.format(x))
            ids.append(id)
            
        return ids
    
    
    def get_loops(self, items=None):
        if items is None: 
            return list(self.loops.values())
        
        loops = []
        for x in items:
            if not isinstance(x, asyncio.BaseEventLoop):
                if x not in self.loops:
                    raise ValueError(x)
                loop = self.loops[x]
            elif x in self.loops.values():
                loop = x
            else:
                raise ValueError('Not existing loop: {}'.format(x))
            loops.append(loop)
            
        return loops
    
    
    def _create_id(self, channel, loop_ids):
        id = 0
        for loop_id in loop_ids:
            ids = self.storage[channel].get(loop_id,{}).keys()
            int_ids = (x for x in ids if isinstance(x,int))
            try: id = max(id, max(int_ids)+1)
            except ValueError: pass
        return id
    
    def _print(self):
        print(self.storage)
        print({_id: id(loop) for _id,loop in self.loops.items()})
        

class Event:
    __slots__ = ('id','type','data','ts')
    
    def __init__(self, id, type, data):
        self.id = id
        self.type = type
        self.data = data
        self.ts = time.time()
        
        
    def __getitem__(self, index):
        return (self.id, self.type, self.data, self.ts)[index]
    
    def __iter__(self):
        return iter((self.id, self.type, self.data, self.ts))
      
        
        
def force_put(queue, item):
    nr_removed = 0
    while True:
        try: queue.put_nowait(item)
        #multiprocessing.Queue also raises queue.Full
        except (_queue.Full,asyncio.QueueFull):
            try: queue.get_nowait()
            except (_queue.Full,asyncio.QueueEmpty): pass
            else: nr_removed += 1
        else: break
    return nr_removed


def empty_queue(queue, return_items=False):
    nr_removed = 0
    received = []
    try:
        while True:
            item = queue.get_nowait()
            if return_items:
                received.append(item)
            else:
                nr_removed += 1
    except (_queue.Empty,asyncio.QueueEmpty):
        pass
    return received if return_items else nr_removed
