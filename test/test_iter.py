from collections import namedtuple, deque
from copy import deepcopy
import pandas as pd
import numpy as np
import pytest

from fons.iter import (unique, flatten, flatten_dict, fliter,
                       sequence_insert)

nd = namedtuple('nd',('a'))
nd2 = namedtuple('nd2',('a b'))

test0 = [2, 4, 2, 'a', 'a', {6}, {6}, (8,), (8,), (9,{10:11}),
         nd(1), (9,{10:11}), nd(1), nd(-2), nd2(-2,-3), {4:5}, '6', {4:5, 6:7}]

expected0 = \
        [2, 4, 'a', {6}, (8,), (9,{10:11}),
         nd(1), nd(-2), nd2(-2,-3), {4:5}, '6', {4:5, 6:7}]
        
expected0_with_key = \
        [2, 4, 'a', {6}, (8,), (9,{10:11}),
         nd(1), nd(-2), {4:5}, '6']
        
expected0_with_op_is = \
        [2, 4, 'a', {6}, {6}, (8,), (8,), (9,{10:11}),
         nd(1), (9,{10:11}), nd(1), nd(-2), nd2(-2,-3), {4:5}, '6', {4:5, 6:7}]

def key0(x):
    if hasattr(x, 'a'):
        return x.a
    elif isinstance(x, dict):
        return x[4]
    else: 
        return x

uq_params = [
    [
        test0, None, None, list,
        expected0,
    ],
    [
        iter(test0), None, None, list,
        expected0,
    ],
    [
        test0, lambda x: x, None, tuple,
        tuple(expected0),
    ],
    [
        test0, key0, None, list,
        expected0_with_key,
    ],
    [
        test0, None, '==', list,
        expected0,
    ],
    [
        test0, None, lambda x,y: x==y, list,
        expected0,
    ],
    [
        test0, None, lambda x,y: x is y, list,
        expected0_with_op_is,
    ],  
]

@pytest.mark.parametrize('x,key,op,astype,expected',uq_params)
def test_unique(x, key, op, astype, expected):
    assert(unique(x, key, op, astype)) == expected


#---------------

def fl_inp():
    x = [[2,3], 4, range(5,7),
         [8, '9.0', map(lambda x: x*2, [11,12,13]), (x for x in [100,101,(y for y in [102,103])])],
         {105,106}, iter({105,106}),
         {1:'1'}, iter({1:'1'}),
         {2:'2'}.keys(), iter({2:'2'}.keys()),
         {3:'3'}.values(), iter({3:'3'}.values()),
         {4:'4'}.items(), iter({4:'4'}.items()),
         (5,), iter((5,)),
         [6], iter([6]),
         np.asarray((7,)), iter(np.asarray((7,))),
         pd.Index([8]), iter(pd.Index([8])),
         range(9,10), iter(range(9,10)),
         enumerate([10]), iter(enumerate([10])),
         '11', iter('11'),
         ]
    return x

fl_expected0 = \
    [2,3,4,5,6,8,'9.0',22,24,26,100,101,102,103,105,106,105,106,
     {1:'1'},1,2,2,'3','3',4,'4',4,'4',5,5,6,6,7,7,8,8,9,9,
     0,10,0,10,'11','1','1']
    
fl_expected0_exclude_set = \
    [2,3,4,5,6,8,'9.0',22,24,26,100,101,102,103,{105,106},105,106,
     {1:'1'},1,2,2,'3','3',4,'4',4,'4',5,5,6,6,7,7,8,8,9,9,
     0,10,0,10,'11','1','1']
    
fl_expected0_include_dict = \
    [2,3,4,5,6,8,'9.0',22,24,26,100,101,102,103,105,106,105,106,
     1,1,2,2,'3','3',4,'4',4,'4',5,5,6,6,7,7,8,8,9,9,
     0,10,0,10,'11','1','1']
    
fl_expected0_include_all = \
    [2,3,4,5,6,8,'9','.','0',22,24,26,100,101,102,103,105,106,105,106,
     1,1,2,2,'3','3',4,'4',4,'4',5,5,6,6,7,7,8,8,9,9,
     0,10,0,10,'1','1','1','1']

fl_params = [
    [
        fl_inp(), (), (), list,
        fl_expected0,
    ],
    [
        iter(fl_inp()), (), (), tuple,
        tuple(fl_expected0),
    ],
    [
        fl_inp(), (), [set], list,
        fl_expected0_exclude_set,
    ],
    [
        fl_inp(), (dict,), (), list,
        fl_expected0_include_dict,
    ],
    [
        fl_inp(), 'all', (), list,
        fl_expected0_include_all,
    ], 
]

@pytest.mark.parametrize('x,include_types,ignore_types,astype,expected',fl_params)
def test_flatten(x, include_types, ignore_types, astype, expected):
    assert(flatten(x, include_types, ignore_types, astype)) == expected
    
    
def test_flatten_dict():
    assert(flatten_dict(fl_inp(), astype=list)) == fl_expected0_include_dict
    
    
def test_fliter():
    assert(fliter(fl_inp(), astype=list)) == fl_expected0_include_all
    
    
#---------------

seq_insert_params = [
    [
        [0,1,2,3,5,11,17,19],
        [2,3,7,11],
        None,
        'drop',
        [0,1,2,3,5,7,11,17,19],
    ],
    [   
        [['a',0],['a',1],['a',2],['a',3],['a',5],['a',11],['a',17],['a',19]],
        [['',2],['',3],['',7],['',11]],
        lambda x: x[1],
        'drop',
        [['a',0],['a',1],['a',2],['a',3],['a',5],['',7],['a',11],['a',17],['a',19]],
    ],
    [
        [0,1,2,3,5,11,17,19],
        [2,3,7,11],
        None,
        'keep',
        [0,1,2,2,3,3,5,7,11,11,17,19],
    ],
    [   
        [['a',0],['a',1],['a',2],['a',3],['a',5],['a',11],['a',17],['a',19]],
        [['',2],['',3],['',7],['',11]],
        lambda x: x[1],
        'keep',
        [['a',0],['a',1],['',2],['a',2],['',3],['a',3],['a',5],['',7],['',11],['a',11],['a',17],['a',19]],
    ]
]
seq_insert_params += [
        [x[0], deque(x[1]), x[2], x[3], deque(x[4])]
    for x in deepcopy(seq_insert_params)]
#deque(x, maxlen=n) keeps only x[-n:]
seq_insert_params += [
        [x[0], deque(x[1], maxlen=8), x[2], x[3], deque(x[4], maxlen=8)]
    for x in deepcopy(seq_insert_params)]


@pytest.mark.parametrize('seq,ins_to,key,duplicates,expected',seq_insert_params)
def test_sequence_insert(seq, ins_to, key, duplicates, expected):
    sequence_insert(seq, ins_to, key=key, duplicates=duplicates)
    assert ins_to == expected
