import asyncio
import time
import functools
import queue as _queue
from collections import defaultdict, namedtuple, Counter
from concurrent.futures import Future

from fons.aio import call_via_loop, call_via_loop_afut
from fons.func import get_arg_count
import fons.log as _log
from fons.reg import create_name

logger, logger2, tlogger, tloggers, tlogger0 = _log.get_standard_5(__name__)

ROOT = "temporary"
_STATION_NAMES = set()
_TRANSMITTER_NAMES = set()
_NODE_NAMES = set()
_empty = object()
_qeitem = namedtuple("qe", "queue event")
_node_id = -1


def set_root(value):
    global ROOT
    ROOT = value


class Transmitter:
    def __init__(self, name=None):
        self._receptors = []
        # self._loops = Counter()
        self.name = create_name(name, self.__class__.__name__, _TRANSMITTER_NAMES)

    # def get_loops(self):
    #    return [loop for loop, count in self._loops.items() if count]

    def __iadd__(self, receptor):
        self.prepare(receptor)
        self._receptors.append(receptor)
        # loop = getattr(receptor,'_loop',None)
        # if isinstance(loop, asyncio.BaseEventLoop):
        #    self._loops[loop] += 1
        return self

    def __isub__(self, receptor):
        self._receptors.remove(receptor)
        # loop = getattr(receptor,'_loop',None)
        # if isinstance(loop, asyncio.BaseEventLoop):
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
        # If loop is not running then thread safety doesn't matter, right?
        # (or unless multiple threads are accessing the queue simultaneously?)
        else:
            f()

    @staticmethod
    def _call_all(partials):
        for f in partials:
            f()


class EventTransmitter(Transmitter):
    """Contains events"""

    def fire(self, *, op="set", **kw):
        """set/clear all events"""
        if not isinstance(op, str):
            op = "set" if bool(op) else "clear"
        loop_partials = defaultdict(list)

        for event in self._receptors:
            loop = event._loop if isinstance(event, asyncio.Event) else None
            loop_partials[loop].append(getattr(event, op))

        if kw.get("return_partials"):
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

        if kw.get("return_partials"):
            return loop_partials

        self.fire_loop_partials(loop_partials)

    def _put_to_queue(self, q, r):
        nr_forced = force_put(q, r)
        if nr_forced:
            qname = getattr(q, "name", "")
            qnstr = " '{}'".format(qname) if qname else ""
            if getattr(q, "warn", True):
                logger2.warn(
                    "{} - had to discard {} item(s) in queue{}".format(
                        self.name, nr_forced, qnstr
                    )
                )
            q.messages_undelivered += nr_forced
        else:
            q.messages_behind += 1


class Station:
    def __init__(
        self,
        data=[],
        default_queue_size=0,
        default_queue_cls=asyncio.Queue,
        default_event_cls=asyncio.Event,
        *,
        name=None,
        loops=[]
    ):
        self.storage = {}
        self.qtransmitters = {}
        self.etransmitters = {}
        self.channels = set()
        # maxsize 0 is infinite
        self.default_queue_size = default_queue_size
        self.default_queue_cls = default_queue_cls
        self.default_event_cls = default_event_cls
        self.channel_default_queue_sizes = {}
        self.name = create_name(name, self.__class__.__name__, _STATION_NAMES)
        # default loop for adding new queue/event
        # if left to None, add will use .get_event_loop()
        self._current_loop_id = 0
        self.loops = {}
        if isinstance(loops, dict):
            for loop_id, loop in loops.items():
                self.add_loop(loop, loop_id)
        else:
            for loop in loops:
                self.add_loop(loop)

        for item in data:
            if item["channel"] not in self.channels:
                self.add_channel(item["channel"], item.get("default_queue_size"))
            item2 = {x: y for x, y in item.items() if x not in ("default_queue_size",)}
            # if
            if "id" in item2:
                self.add(**item2)

    def add_channel(self, channel, default_queue_size=None):
        if channel in self.channels:
            raise ValueError("Channel {} already added".format(channel))
        self.channels.add(channel)
        self.qtransmitters[channel] = QueueTransmitter(self.name + "[QT]")
        self.etransmitters[channel] = EventTransmitter(self.name + "[ET]")
        self.storage[channel] = defaultdict(dict)
        self.channel_default_queue_sizes[channel] = default_queue_size

    def add_loop(self, loop=None, id=None):
        if id is None:
            id = self._current_loop_id
        if loop is None:
            loop = asyncio.get_event_loop()

        if id in self.loops:
            raise ValueError("Already taken id: {}".format(id))
        """elif loop in self.loops.values():
            raise ValueError('Already existing loop: {}'.format(loop))"""

        self.loops[id] = loop

        if isinstance(id, int):
            self._current_loop_id = max(self._current_loop_id, id + 1)
        return id

    def add(self, channel, id=None, queue=None, event=None, maxsize=None, loops=None):
        if maxsize is None:
            maxsize = self.channel_default_queue_sizes[channel]
        if maxsize is None:
            maxsize = self.default_queue_size

        if (
            queue is not None
            and event is not None
            and isinstance(queue, asyncio.Queue)
            and isinstance(event, asyncio.Event)
            and queue._loop is not event._loop
        ):
            raise ValueError("Queue's loop doesn't match with event's loop")

        if loops is None:
            if queue is not None and isinstance(queue, asyncio.Queue):
                loops = [queue._loop]
            elif event is not None and isinstance(event, asyncio.Event):
                loops = [event._loop]
        loop_ids = self.get_loop_ids(loops, add=True)
        # if id is None:
        #    id = getattr(queue,'id',None)
        if id is None:
            id = self._create_id(channel, loop_ids)

        items = {}
        for loop_id in loop_ids:
            loop = self.loops[loop_id]
            _queue, _event = queue, event

            if queue is False:
                _queue = None
            elif queue is None:
                kw = {"loop": loop} if self.default_queue_cls is asyncio.Queue else {}
                _queue = self.default_queue_cls(maxsize, **kw)
            elif isinstance(queue, asyncio.Queue) and queue._loop is not loop:
                raise ValueError(
                    "Loop <{}> doesn't match with provided queue's loop".format(loop_id)
                )

            if event is False:
                _event = None
            elif event is None:
                kw = {"loop": loop} if self.default_event_cls is asyncio.Event else {}
                _event = self.default_event_cls(**kw)
            elif isinstance(event, asyncio.Event) and event._loop is not loop:
                raise ValueError(
                    "Loop <{}> doesn't match with provided event's loop".format(loop_id)
                )

            if _queue is None and _event is None:
                continue

            new = _qeitem(_queue, _event)

            if id in self.storage[channel].get(loop_id, {}):
                raise ValueError(
                    'Id "{}" has already been added to channel "{}"'.format(id, channel)
                )

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
        items = self.add(channel, id, queue, False, maxsize, loops=loops)
        return {loop_id: x.queue for loop_id, x in items.items()}

    def add_event(self, channel, id=None, event=None, loops=None):
        items = self.add(channel, id, False, event, loops=loops)
        return {loop_id: x.event for loop_id, x in items.items()}

    def remove(self, channel, id, loops=None):
        """Does NOT raise error on non-existent"""
        loop_ids = self.get_loop_ids(loops)

        for loop_id in loop_ids:
            try:
                item = self.storage[loop_id].pop(id)
            except KeyError:
                continue
            if item.queue is not None:
                self.qtransmitters[channel] -= item.queue
            if item.event is not None:
                self.etransmitters[channel] -= item.event

    def broadcast(self, channel, *put, op="set"):
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
            if "channel" in d:
                channel = d["channel"]
            elif "_" in d:
                channel = d["_"]
            else:
                raise KeyError('Missing keyword "channel" or "_"; got: {}'.format(d))

            qt_loop_partials = et_loop_partials = {}

            if "put" in d:
                item = d["put"]
                qt_loop_partials = self.qtransmitters[channel].fire(
                    item, return_partials=True
                )

            if "op" in d:
                op = d["op"]
                et_loop_partials = self.etransmitters[channel].fire(
                    op=op, return_partials=True
                )

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
        elif hasattr(ids, "__iter__") and not isinstance(ids, str):
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
                try:
                    id = next(id for id, loop in self.loops.items() if loop is x)
                except StopIteration:
                    if not add:
                        raise ValueError("Not existing loop: {}".format(x))
                    id = self.add_loop(x)
            elif x in self.loops:
                id = x
            else:
                raise ValueError("Not existing id: {}".format(x))
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
                raise ValueError("Not existing loop: {}".format(x))
            loops.append(loop)

        return loops

    def _create_id(self, channel, loop_ids):
        id = 0
        for loop_id in loop_ids:
            ids = self.storage[channel].get(loop_id, {}).keys()
            int_ids = (x for x in ids if isinstance(x, int))
            try:
                id = max(id, max(int_ids) + 1)
            except ValueError:
                pass
        return id

    def _print(self):
        print(self.storage)
        print({_id: id(loop) for _id, loop in self.loops.items()})


class Event:
    __slots__ = ("id", "type", "data", "ts")

    def __init__(self, id, type, data):
        self.id = id
        self.type = type
        self.data = data
        self.ts = time.time()

    def __getitem__(self, index):
        return (self.id, self.type, self.data, self.ts)[index]

    def __iter__(self):
        return iter((self.id, self.type, self.data, self.ts))


class RelayPackage:
    __slots__ = ("data", "source", "handler", "channel", "current_handler")

    def __init__(
        self, data, source=None, handler=None, channel=None, current_handler=None
    ):
        """
        :type source: Node
        :type handler: Handler
        :type current_handler: Handler
        """
        self.data = data
        self.source = source
        self.handler = handler
        self.channel = channel
        self.current_handler = current_handler

    def copy(self, **kw):
        return self.__class__(
            **dict(
                {
                    "data": self.data,
                    "source": self.source,
                    "handler": self.handler,
                    "channel": self.channel,
                    "current_handler": self.current_handler,
                },
                **kw
            )
        )


class RelayInfo:
    __slots__ = ("items",)

    def __init__(self, items=[]):
        self.items = list(items)

    def add_item(self, value, channels):
        self.items.append((value, channels))


class NodeExit:
    """Put this into node to signal it to stop listening"""

    pass


class Node:
    def __init__(
        self, clients=[], handlers=[], groups=[], *, loop=None, root=None, name=None
    ):
        """
        Node ids are negative, as are the station channels reserved for them individually.
        Channels grouping multiple nodes together must be positive or non-int.
        Handlers are functions that input the RelayPackage received by the ._queue,
         output a value, which is then wrapped with RelayPackage and forwarded to
         all channels associated with the handler.
        Channel <0> contains all connected nodes, which is also the default channel of the root_handler.
        :param root:
            about .root_handler (which forwards the unadulterated data to all connected nodes)
            ::None: defaults to ROOT ("temporary" by default)
            ::True: root handler will be added on initiation
            ::"temporary": -||-, but removed when .add_handler is called the first time
                           (including in `handlers` argument)
            ::"temp": == "temporary"
            ::False: root handler will not be added
        To start serving:
            node.serve()
        """
        global _node_id

        if name is None:
            name = abs(_node_id)

        self.id = _node_id
        self.name = create_name(
            name, default=self.__class__.__name__, registry=_NODE_NAMES
        )

        _node_id -= 1

        # Initiate with channel 0
        self.station = Station([{"channel": 0}])
        self._queue = asyncio.Queue(loop=loop)
        # self._user_queue = asyncio.Queue(maxlen=self.user_maxlen, loop=loop)
        self.loop = self._queue._loop
        self.futures = {"serve": None}
        self.handlers = []

        # ie nodes that receive from (the handlers of) this node
        self.clients_by_id = {}
        # ie the channels that each client receives from
        self.client_channels = {}

        self._last_handler_id = -1
        if root is None:
            root = ROOT
        self._root = root
        self._root_handler_overriden = False
        # Root handler just forwards the received data to all connected nodes
        # it will be removed as soon as the first handler is added
        self.root_handler = NodeHandler(self, lambda x: x.data, [0], id="root")

        if root:
            self.handlers.append(self.root_handler)

        for node_specs in clients:
            kwargs = node_specs[1] if len(node_specs) > 1 else {}
            self.connect(*node_specs[0], **kwargs)

        for group_specs in groups:
            kwargs = group_specs[1] if len(group_specs) > 1 else {}
            self.group(*group_specs[0], **kwargs)

        for handler_specs in handlers:
            kwargs = handler_specs[1] if len(handler_specs) > 1 else {}
            self.add_handler(*handler_specs[0], **kwargs)

    def connect(self, node, *channels):
        """Add recipient node"""
        if not isinstance(node, Node):
            raise TypeError("`node` must be of type Node, got: {}".format(type(node)))
        if node.id in self.clients_by_id:
            raise ValueError("Node <{}> has already been added".format(node.id))

        if node.id not in self.station.channels:
            self.station.add_channel(node.id)

        self.clients_by_id[node.id] = node
        self.station.add_queue(node.id, id=0, queue=node._queue)
        self.station.add_queue(0, id=node.id, queue=node._queue)

        for channel in channels:
            self.group(channel, node)

        self.client_channels[node.id] = set([node.id])

    def disconnect(self, node):
        """Deletes all traces of the node. The channels in handlers' lists remain,
        but the channel itself just doesn't contain the node any more."""
        if not isinstance(node, Node):
            node = self.clients_by_id[node]
        del self.clients_by_id[node.id]
        # station.remove doesn't raise error on non-existent
        self.station.remove(node.id, id=0)
        self.station.remove(0, id=node.id)
        client_channels = self.client_channels[node.id]
        for channel in client_channels:
            self.station.remove(channel, id=node.id)
        del self.client_channels[node.id]

    def group(self, channel, *nodes):
        """Registers the given nodes under the channel"""
        if isinstance(channel, int) and channel <= 0:
            raise ValueError("Channel must be > 0, got: {}".format(channel))

        if channel not in self.station.channels:
            self.station.add_channel(channel)

        for node in nodes:
            if not isinstance(node, Node):
                node = self.clients_by_id[node]
            self.station.add_queue(channel, id=node.id, queue=node._queue)
            self.client_channels[node.id].add(channel)

    def ungroup(self, channel, *nodes):
        """Disassociates the given nodes from the channel"""

        if isinstance(channel, int) and channel < 0:
            raise ValueError("Channel must be >= 0, got: {}".format(channel))

        for node in nodes:
            if not isinstance(node, Node):
                node = self.clients_by_id[node]
            self.station.remove(channel, id=node.id)
            self.client_channels[node.id].remove(channel)

    def add_handler(self, f, *recipients, id=None, loop=None, type=None):
        if loop is None:
            loop = self.loop
        if not isinstance(f, NodeHandler):
            handler = NodeHandler(self, f, id=id, loop=loop, type=type)
        else:
            handler = f
            if handler.node != self:
                raise ValueError("Handler connected to wrong node.")
        for rcp in recipients:
            handler.add_recipient(rcp)
        if not self._root_handler_overriden and self._root in ("temp", "temporary"):
            try:
                self.remove_handler(self.root_handler)
            except ValueError:
                pass
            self._root_handler_overriden = True
        self.handlers.append(handler)

        return handler

    def remove_handler(self, handler):
        """:param handler: NodeHandler or its id"""
        if not isinstance(handler, NodeHandler):
            id = handler
            handler = next((x for x in self.handlers if x.id == id), None)
            if handler is None:
                raise ValueError("No handler matching id: {}".format(id))
        self.handlers.remove(handler)

    def has_client(self, node):
        """:param node: Node or its id"""
        node_id = node.id if isinstance(node, Node) else node

        return node_id in self.clients_by_id

    def serve(self):
        """Start listening and handling any received."""
        if self.is_running():
            return
        self.futures["serve"] = call_via_loop_afut(self._serve, loop=self.loop)

    async def _serve(self):
        try:
            while True:
                inp = await self._queue.get()
                if isinstance(inp, NodeExit):
                    break
                self.handle(inp)
        finally:
            for handler in self.handlers:
                handler.stop()

    def handle(self, inp):
        for handler in self.handlers:
            handler.handle(inp)

    async def recv(self):
        """Receive directly, skipping the handlers"""
        if self.is_running():
            raise RuntimeError("Cannot receive directly while node is running.")

        return await self._queue.get()

    def recv_nowait(self):
        return self._queue.get_nowait()

    def relay(self, data, *channels):
        """Relays directly, skipping the handlers"""
        if not channels:
            channels = [0]
        pks = [RelayPackage(data, self, None, channel) for channel in channels]
        self.station.broadcast_multiple(
            [{"channel": pk.channel, "put": pk} for pk in pks]
        )

    def put(self, x, ensure_is_packed=True):
        """
        Put something into node's input queue
        (if node is running it is immediately received by all its handlers).
        :rtype: asyncio.Future
        """
        if ensure_is_packed and not isinstance(x, RelayPackage):
            x = RelayPackage(x, None, None, None)

        return call_via_loop_afut(self._queue.put, (x,), loop=self._queue._loop)

    def put_nowait(self, x, ensure_is_packed=True):
        """:rtype: Future"""
        if ensure_is_packed and not isinstance(x, RelayPackage):
            x = RelayPackage(x, None, None, None)

        return put_via_loop(self._queue, x)

    def empty(self):
        return self._queue.empty()

    def full(self):
        return self._queue.full()

    def is_running(self):
        return self.futures["serve"] is not None and not self.futures["serve"].done()

    def stop(self):
        self.put(NodeExit())

    def __repr__(self):
        return "{}(id={},name={})".format(self.__class__.__name__, self.id, self.name)


class NodeHandler:
    def __init__(
        self, node, target=None, recipients=[], *, loop=None, id=None, type=None
    ):
        """
        :type node: Node
        Handles the input received by its node.
        :param type:
            describes the `target`
            ::None    - target is synchronous function
                         - accepts the node input* as its first argument
                         - returns output (which is then relayed by the handler)
            ::"async" - a continuous "listener" coroutine function that
                         - *may* accept `handler` (self) as its first argument
                         - receives node input by awaiting on handler.recv(),
                         - relays the output data independently (handler.relay(data))
                         - exits on NodeExit()
            ::"gen"   - a function that returns generator
                         - function *may* accept `handler` (self) as its first argument
                        where the generator
                         - receives node input via `yield` keyword
                         - yields the output (which is then relayed by the handler)
                         - exhausts on NodeExit()
            * node input: The data received by node, which is assumed to be wrapped with RelayPackage,
                          or will be (in .handle) if not already done so
        """
        self.node = node
        if loop is None:
            loop = node.loop
        self._queue = asyncio.Queue(loop=loop)
        self.loop = self._queue._loop
        self.channels = []

        self.target = target
        if type not in ("async", "gen", None):
            raise ValueError(type)
        self._type = type
        # if asyncio.iscoroutinefunction(target):
        #    self._type = 'async'

        if id is None:
            self.node._last_handler_id += 1
            id = self.node._last_handler_id
        else:
            if any(x.id == id for x in self.node.handlers):
                raise ValueError("A handler with id <{}> already exits".format(id))
            if isinstance(id, int):
                self.node._last_handler_id = max(id, self.node._last_handler_id)

        self.id = id
        self._started = False

        for rcp in recipients:
            self.add_recipient(rcp)

    def _start(self):
        if self._started:
            return

        args = (self,) if get_arg_count(self.target) else ()

        if self._type is None:
            pass
        elif self._type == "gen":
            self._gen = self.target(*args)
            self._gen.send(None)
        else:
            call_via_loop(self.target, args, loop=self.loop)
        self._started = True

    def handle(self, x):
        if not isinstance(x, RelayPackage):
            x = RelayPackage(x, None, None, None, self)
        else:
            x = x.copy(current_handler=self)

        if self._type is None:
            data = self.target(x)
            self.relay(data)
        elif self._type == "gen":
            # Generator
            self._start()
            data = self._gen.send(x)
            self.relay(data)
        else:
            # Asynchronous
            self._start()
            self.put(x)

    async def recv(self):
        """This is only meant to be used in *asynchronous* target function of the handler"""
        return await self._queue.get()

    def recv_nowait(self):
        return self._queue.get_nowait()

    def relay(self, data):
        """Relay the handler-processed data (wrapped with RelayPackage) to handler's nodes"""
        if isinstance(data, RelayInfo):
            return self._relay_by_info(data)

        # Also include the source node (self) and the associated channel
        pks = [
            RelayPackage(data, self.node, self, channel) for channel in self.channels
        ]
        self.node.station.broadcast_multiple(
            [{"channel": pk.channel, "put": pk} for pk in pks]
        )

    def _relay_by_info(self, info):
        """:type info: RelayInfo"""
        pks = []

        for data, to_channels in info.items:
            for channel in to_channels:
                pk = RelayPackage(data, self.node, self, channel)
                pks.append(pk)

        self.node.station.broadcast_multiple(
            [{"channel": pk.channel, "put": pk} for pk in pks]
        )

    def add_recipient(self, channel, create=False):
        """:param channel: channel or Node"""
        node = None
        if isinstance(channel, Node):
            node = channel
            channel = node.id

        if channel not in self.node.station.channels:
            if not create:
                raise ValueError("Channel <{}> hasn't been added yet".format(channel))
            if node is not None:
                self.node.connect(node)
            else:
                self.node.group(channel)

        if channel in self.channels:
            raise ValueError(
                "Channel <{}> already added to handler {}".format(channel, self.id)
            )

        self.channels.append(channel)

    def remove_recipient(self, channel):
        if isinstance(channel, Node):
            channel = channel.id
        self.channels.remove(channel)

    def put(self, x, ensure_is_packed=True):
        """
        Put something into handler's input queue
        (only received if the handler has asynchronous target)
        :rtype: asyncio.Future
        """
        if ensure_is_packed and not isinstance(x, RelayPackage):
            x = RelayPackage(x, None, None, None)

        return call_via_loop_afut(self._queue.put, (x,), loop=self._queue._loop)

    def put_nowait(self, x, ensure_is_packed=True):
        """:rtype: Future"""
        if ensure_is_packed and not isinstance(x, RelayPackage):
            x = RelayPackage(x, None, None, None)

        return put_via_loop(self._queue, x)

    def empty(self):
        return self._queue.empty()

    def full(self):
        return self._queue.full()

    def is_running(self):
        return self._started

    def stop(self):
        if not self._started:
            return
        if self._type is None:
            pass
        elif self._type == "gen":
            try:
                self._gen.send(NodeExit())
            except StopIteration:
                pass
        else:
            self.put(NodeExit())
        self._started = False


def force_put(queue, item):
    nr_removed = 0
    while True:
        try:
            queue.put_nowait(item)
        # multiprocessing.Queue also raises queue.Full
        except (_queue.Full, asyncio.QueueFull):
            try:
                queue.get_nowait()
            except (_queue.Full, asyncio.QueueEmpty):
                pass
            else:
                nr_removed += 1
        else:
            break
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
    except (_queue.Empty, asyncio.QueueEmpty):
        pass
    return received if return_items else nr_removed


def put_via_loop(queue, x):
    """Put something into queue"""
    p = functools.partial(queue.put_nowait, x)
    if asyncio.get_event_loop() is queue._loop:
        f = Future()
        f.set_result(p())
        return f
    else:
        return call_via_loop(p, loop=queue._loop)
