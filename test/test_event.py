import asyncio

from fons.event import Node

loop = asyncio.get_event_loop()
lrc = loop.run_until_complete


def test_node():
    n = Node()
    n2 = Node()
    n3 = Node()
    n.connect(n2)
    n.connect(n3)
    
    message = 'Something'
    n.relay(message)
    
    pk2 = lrc(n2.recv())
    assert pk2.data == message
    
    pk3 = lrc(n3.recv())
    assert pk3.data == message
    