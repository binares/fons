import os
from collections import OrderedDict as OD
import pandas as pd
import numpy as np
import datetime
dt = datetime.datetime
td = datetime.timedelta
import copy
import pprint as pp
import traceback
import pytest

import fons.verify as vfy
from fons.verify import (
    Element, Container, Multi, Value, MultiVal, Type, Int, Float, Bool, Str, Null,
    Set, List, Dict, NullDict, Dtyct,
)


DNFO = {'tch': {'_type_': pd.DataFrame,
                'dtypes':OD(zip(['prc','vol_b','vol_s','vol','volC'],[float]*5))},
        
        'mh':  {'_type_': pd.DataFrame,
                'dtypes':OD([['TimeStamp','datetime64[ns]'],
                            ['OrderType',str],
                            ['Price',float],
                            ['Quantity',float],
                            ['Total',float],
                            ['Id',int],
                            ['FillType',str]])},
        'obs': {'_type_': list},
        'pvhist': {'_type_': dict,
                   'items': {'_prh':{'_type_':list,
                                     'unit':{'_type_':float}},
                             '_vlh24':{'_type_':list},
                             '_timestamps':{'_type_':dict,
                                            'items':{'timestamps': {'_type_':list},
                                                     'new_timestamps':{'_type_':list},
                                                     'indexes': {'_type_':list},
                                                     'new_vol24stamps':{'_type_':list}}
                                            }
                             }
                   },
        
        'prc': {'_type_': float,
                '_defval_': np.nan},
        
        'vol24':{'_type_': float,
                 '_defval_': np.nan},
        #}
        
        'news': {'_type_': pd.DataFrame,
                 'data':OD([['TimeStamp',dt(2000,1,1)],
                            ['TimeObtained',dt(2000,1,2)],
                            ['TimeForwarded',dt(2000,1,3)],
                            ['TimeForwarded2',dt(2000,1,14)],
                            ['Id',0],
                            ['Source','asource'], #'Twitter' or 'Reddit' 
                            ['UserName','auser'],
                            ['UserId','auserid'],
                            ['InReplyTo','ainreplyto'], #user's screen name
                            ['Text','atext'],
                            ['TextHighlighted','atexthighlighted'],
                            ['+',0],
                            ['-',1],
                            ['O',2],
                            ['Link','alink'],
                            ['RetweetCount',3],
                            ['FavoriteCount',4],
                            ['Mentions','amentions'],
                            ['Forward',True]]),
                 'dtypes': OD([['TimeStamp','datetime64[ns]'],
                            ['TimeObtained','datetime64[ns]'],
                            ['TimeForwarded','datetime64[ns]'],
                            ['TimeForwarded2','datetime64[ns]'],
                            ['Id',str],
                            ['Source',str], #'Twitter' or 'Reddit' 
                            ['UserName',str],
                            ['UserId',str],
                            ['InReplyTo',str], #user's screen name
                            ['Text',str],
                            ['TextHighlighted',str],
                            ['+',int],
                            ['-',int],
                            ['O',int],
                            ['Link',str],
                            ['RetweetCount',int],
                            ['FavoriteCount',int],
                            ['Mentions',str],
                            ['Forward',bool]])},

                 
        'signals': {'_type_':list,
                    'unit': {'_type_':dict,
                            'dtypes':OD([['id',str],
                                         ['uid',int],
                                        ['market',str],
                                        ['ts',dt],
                                        ['prc',{'_type_': dict,
                                                 'dtypes':OD([
                                                            ['open',float],
                                                            ['close',float],
                                                            ['incr',float],
                                                            ['cd',float],
                                                            ['param_pos',int],
                                                            ['incr24',float]])}],
                                         ['vol',{'_type_': dict,
                                                 'dtypes':OD([
                                                            ['vol',float],
                                                            ['ratio',float],
                                                            ['ratio24',float]])}]])
                               }
                    },
        'X': {'_type_': 'type',
              '_value_': 'pd.DataFrame'},
        'Y': {'_type_': type,
              '_value_': list},
        'Z': {'_type_': 'type',
              '_value_': 'type'},}
 
           

_unitN = {'_type_': type(None), '_value_': None}
_unitNAT = {'_type_': type(pd.NaT), '_call_': None}

_unitT = {'_type_': bool, '_value_': True}
_unitF = {'_type_': bool, '_value_': False}
_unitB = {'_type_': bool, '_call_': None}

_unitDT = {'_type_': dt, '_call_': None}
_unitTD = {'_type_': td, '_call_': None}
_unitnpDT = {'_type_': np.datetime64, '_call_': None}
_unitnpTD = {'_type_': np.timedelta64, '_call_': None}

_TPtypes = (dt, td, np.datetime64, np.timedelta64, bool)

#both work:
_multiunit = {'_multi_': [_unitDT, _unitTD, _unitN, _unitnpDT, _unitnpTD]} #_unitNAT (not necessary)
#_multiunit = {'_type_': (dt,td,type(None),np.datetime64,np.timedelta64), '_call_':None}


TP_IN = {'_defval_': _unitN,
         '_multi_':[{'_type_':'listlike', 'size': {'max': 2}, 'unit': _multiunit, '_call_': None},
                    #_unitDT, _unitTD, _unitnpDT,_unitnpTD, _unitB,]} # _unitNAT]} #_unitT, _unitF
                    {'_type_': _TPtypes, '_call_': None}]}

TP_OUT = {'_defval_': _unitN,
          '_type_':tuple,
          'size': 2,
          'unit': {'_type_': (dt,type(None)), '_call_': None, 'sub': False}}

#sub = False necessary due to pandas NaT being subtype of dt
#however pd.Timestamp is still valid, due to _type2a = _map(_type2) in verify_data

DNFO['tp'] = TP_IN


MH = DNFO['mh']
mh_dtps = DNFO['mh']['dtypes']
t_mh = pd.DataFrame(columns=mh_dtps.keys())
for c,dtype in mh_dtps.items(): t_mh[c] = t_mh[c].astype(dtype)
t_mh2 = None

def test_isinstructions():
    assert vfy._isinstructions(MH)
    assert not vfy._isinstructions({'type':{'_type_':2}})
                                

def test_copy():
    global t_mh2
    t_mh2 = vfy._copy(t_mh)
    
    assert (t_mh == t_mh2).all().all()
    assert t_mh is not t_mh2


def test_normalize():
    norm = vfy.normalize(MH)
    assert DNFO['mh']['columns'] == list(MH['dtypes'].keys())
    assert (MH['_copy_'] == t_mh).all().all()
    

def test_normalize_element():
    dflt = {'_type_': type(np.nan),
            '_value_': np.nan,
            '_isnorm_': True}

    assert vfy.normalize_element(2,default=np.nan) == {'_type_': int,
                                                       '_value_': 2,
                                                       '_defval_':dflt,
                                                       '_isnorm_':True}

def test_verify_data():
    t_mh3 = t_mh2.copy()
    t_mh3['TimeStamp'] = '2'
    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data(t_mh3,DNFO['mh'])

    t_mh3 = t_mh2.copy()
    t_mh3['E'] = np.nan
    with pytest.raises(vfy.VeriKeyError) as e_info:
        vfy.verify_data(t_mh3,DNFO['mh'])

    MH2 = copy.deepcopy(DNFO['mh'])
    MH2['index'] = [33]
    t_mh3 = vfy.init_data(MH2)
    MH2['index'].append(44)

    with pytest.raises(vfy.VeriKeyError) as e_info:
        vfy.verify_data(t_mh3,MH2)



S = s = None
SIG = DNFO['signals']

def test_init_data():
    data = vfy.init_data(DNFO)
    for k,norm in DNFO.items():
        vfy.verify_data(data[k],norm)

    global S,s
    S = data['signals']
    s = vfy.init_data(SIG['unit'])

    s['uid'] = 8
    s['prc']['incr'] = 2.4
    S.append(s)
    
    #pp.pprint(s)
    #pp.pprint(SIG)
    
    vfy.verify_data(S,DNFO['signals'])


#More verify data tests:
def test_verify_data2():
    s2 = vfy._copy(s)
    #s2['ts'] = #np.nan #None #4.8 #3453253245
    s2['ts'] = pd.Timestamp(dt(2000,1,1))
    S2 = S + [s2]
    #pp.pprint('S2: {}'.format(S2))

    s2['prc']['incr'] = 2
    vfy.verify_data(S2,DNFO['signals'])

    s2['uid'] = 8.3
    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data(S2,DNFO['signals'])

    

    s3 = vfy._copy(s)
    s4 = vfy._copy(s)
    del s3['market']
    s4['vol']['extrakey'] = np.nan
    S3 = S + [s3]
    S4 = S + [s4]
    #pp.pprint('S3 {}'.format(S3))
    #pp.pprint('S4 {}'.format(S4))


    with pytest.raises(vfy.VeriKeyError) as e_info:
        vfy.verify_data(S3,DNFO['signals'])

    with pytest.raises(vfy.VeriKeyError) as e_info:
        vfy.verify_data(S4,DNFO['signals'])
    

def test_fill_missing():
    s5 = s.copy()
    del s5['ts']
    del s5['prc']

    s6 = vfy.fill_missing(s5,SIG['unit'])
    #pp.pprint(s5)
    #pp.pprint(s6)
    #print(list(s6.keys()))
    vfy.verify_data(s5,SIG['unit'])
    vfy.verify_data(s6,SIG['unit'])

nat = type(pd.NaT)
aTP = (dt(2000,1,4),dt(2000,1,6))
aTD = (td(3),td(2))
atp3 = (aTP[0],aTD[1])
atp4 = (aTD[0],aTP[1])
atp5 = (aTP[0],None)
atp6 = (aTD[0],None)
atp7 = (nat(),None)


aTP0 = dt(2000,1,4)
aTD0 = td(2)


atps_tuples = [aTP,aTD,atp3,atp4,atp5,atp6,atp7]
atps_lists = [list(x) for x in atps_tuples]
atps_indexes = [pd.Index(x) for x in atps_tuples[:4]]
try:
    # This requires pandas>=0.25
    atps_indexes += [pd.Index(x) for x in atps_tuples[4:]]
except ValueError:
    pass
#(dt,None) -> (dt,NaT)
#(td,None) -> (td,NaT)
#(NaT,None) -> (NaT,None)

atps_arrays = [np.asarray(x) for x in atps_indexes]
#Note: asarray preserves pandas dtype, if obj has it (and converts to numpy corresponding dtypes)
#Otherwise asarray(tuple(...)) only infers dtype if *all* objects are numpy64 (not pd.Timestamp, pd NaT)
#From pd index to np.ndarray:
#(dt,NaT) -> (np.dt64(..),np.dt64('NaT'))
#(td,NaT) -> (np.td64(..),np.dt64('NaT'))
#(None,None) - > (None,None)
#atps_arrays = atps_indexes = []

atps = atps_tuples + atps_lists + atps_arrays + atps_indexes + [aTP0,aTD0,None,True,False, nat()]

"""pp.pprint(DNFO['tp'])
print("\n")
vfy.init_data(DNFO['tp'])
pp.pprint(DNFO['tp'])
input()"""

@pytest.mark.parametrize("test_input", atps)
def test_verify_data3(test_input):
    vfy.verify_data(test_input,TP_IN)



arr0 = np.asarray([np.nan])
arr = np.asarray([np.nan,nat()])

atps2 = (2.3 , 5, 'sth', np.nan , arr0, arr)
#atps2 += (np.datetime64(dt(2000,1,1)), np.timedelta64(td(2)), (None,td(2)))


@pytest.mark.parametrize("test_input", atps2)
def test_verify_data4(test_input):
    with pytest.raises(vfy.VeriTypeError) as e_info: #VeriError
        vfy.verify_data(test_input,TP_IN)



atps3 = [nat(),np.nan, td(4), True, [], aTP0]
         
@pytest.mark.parametrize("test_input", atps3)
def test_verify_data5(test_input):
    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data(test_input,TP_OUT)



def test_verify_data6():
    vfy.verify_data(None,TP_OUT)
    vfy.verify_data((aTP0,aTP0),TP_OUT)
    vfy.verify_data((aTP0,None),TP_OUT)
    vfy.verify_data((pd.to_datetime(aTP0),None),TP_OUT)

    with pytest.raises(vfy.VeriTypeError) as e_info: #VeriError
        vfy.verify_data((aTP0,td(5)),TP_OUT)

    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data((aTP0, np.datetime64(aTP0)),TP_OUT) #VeriError

    with pytest.raises(vfy.VeriTypeError) as e_info: #VeriError
        vfy.verify_data((aTP0,nat()),TP_OUT)
    
    with pytest.raises(vfy.VeriIndexError) as e_info:
        vfy.verify_data((aTP0,aTP0,aTP0),TP_OUT)

    with pytest.raises(vfy.VeriIndexError) as e_info:
        vfy.verify_data((aTP0,),TP_OUT)



test_verify_range_input = [
    [2, {'_type_': float, 'range': '[0,2'}, vfy.BadInstruction],
    [2, {'_type_': float, 'range': '[2]'}, vfy.BadInstruction],
    [2, {'_type_': float, 'range': '[10,2]'}, vfy.BadInstruction],
    [2, {'_type_': float, 'range': '[0,3.5]'}, None],
    [2, {'_type_': float, 'range': '[0,2]'}, None],
    [2, {'_type_': float, 'range': '[2,2.0]'}, None],
    [2, {'_type_': float, 'range': '[2,2.0)'}, vfy.VeriValueError],
    [29, {'_type_': float, 'range': '[2,]'}, None],
    [-1, {'_type_': float, 'range': '[2,]'}, vfy.VeriValueError],
    [-1.2, {'_type_': float, 'range': '(-3,-1)'}, None],
    [-1.2, {'_type_': float, 'range': '(-3,-1.2)'}, vfy.VeriValueError],
    [-1.2, {'_type_': int, 'range': '(-3,-1.2)'}, vfy.VeriTypeError],
    [-1, vfy.IntRange('(-3,0)'), None],
    [-1.2, vfy.IntRange('(-3,-1.2)'), vfy.VeriTypeError],
    [-1.2, vfy.FloatRange('(-3,-1.2]'), None],
    [-1.2, vfy.FloatRange('(-3,-1.2)'), vfy.VeriValueError],
]

@pytest.mark.parametrize("x,norm,raises", test_verify_range_input)
def test_verify_range(x, norm, raises):
    if raises:
        with pytest.raises(raises):
            vfy.verify_data(x, norm)
    else:
        vfy.verify_data(x, norm)


#------------------
#Tests for some new special cases:
def test_special():
    vfy.verify_data([2,3],[2,3])

    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data([2,3],(2,3))

    with pytest.raises(vfy.VeriValueError) as e_info:
        vfy.verify_data([2,3],[2,5])

    with pytest.raises(vfy.BadInstruction) as e_info:
        vfy.normalize({'_multi_':False})

    with pytest.raises(vfy.VeriTypeError) as e_info:
        vfy.verify_data(OD({2:3}),{'_type_':dict, 'sub':False, '_value_':{2:3}})

    vfy.verify_data(OD({2:3}),{2:3})


"""def test__get_trace_lvl():
    txt = '(0)msg(1)msg(2)msg(2)key(3)msgHEADER(0)'
    e = vfy.VeriError(txt)
    
    assert vfy._get_trace_lvl(e) == 3"""


inp_args = [
    #[
    #:: input_kwargs, 
    #:: expected (handler['type'], handler['key']['missing'], handler['key']['extra']),
    #],
    [
        {'missing': 'fix-', 'type': 'warn', 'mode': 'ignore'},
        ('warn','fix-','ignore'),
    ],
    [
        {'missing': 'fix-', 'extra': 'warn', 'type': 'ignore'},
        ('ignore','fix-','warn'),
    ],
    [
        {'missing': 'fix-', 'key': 'warn'},
        ('error','warn','warn'),
    ],
    [
        {'missing': 'fix-', 'key': 'warn', 'handler': {'key': {'missing': 'ignore'}}},
        ('error','ignore','warn'),
    ],
]

@pytest.mark.parametrize("kwargs,expected", inp_args)
def test__verify_input_args(kwargs, expected):
    if 'mode' not in kwargs:
        kwargs['mode'] = 'error'
        
    vfy._verify_input_args(kwargs)
    handler = kwargs['handler']
    key = handler['key']
    
    assert handler['type'] == expected[0]
    assert key['missing'] == expected[1]
    assert key['extra'] == expected[2]


#------------------

def _verify(element, x, raises):
    if not raises:
        element.verify(x)
    else:
        with pytest.raises(raises):
            element.verify(x)


multi_inp = [
    [2, None],
    [2.0, vfy.VeriTypeError],
    [(258,), vfy.VeriValueError],
    [(259,), None],
    ['22', None],
]

@pytest.mark.parametrize("x,raises", multi_inp)
def test_elements_multi(x, raises):
    multi = Multi(Str, Int, {'_value_': (259,)})
    _verify(multi, x, raises)

 
dict_inp = [
    ['wrongtype', vfy.VeriTypeError],
    [{'a': 8.2}, None],
    [{'x': None}, vfy.VeriTypeError],
    [{'x': 'b'}, vfy.VeriValueError],
    [{'x': 'a'}, None],
    [{'x': 'a', 'n': (17,)}, None],
    [{'x': 'a', 'n': (18,)}, vfy.VeriValueError],
    [{'x': 'a', 'n': [17]}, None],
    [{'x': 7}, None],
]
 
@pytest.mark.parametrize("x,raises", dict_inp)
def test_elements_dict(x, raises):
    dict_ = Dict[float, list, MultiVal((17,), 'a')]
    #print(dict_.to_dict())
    #print(MultiVal((17,)).to_dict())
    _verify(dict_, x, raises)


list_inp = [
    ((258,), vfy.VeriTypeError),
    (None, vfy.VeriTypeError),
    ([None], vfy.VeriTypeError),
    ([2.0], vfy.VeriTypeError),
    ([(258,)], vfy.VeriTypeError),
    ([[258]], vfy.VeriValueError),
    (['12'], None),
    ([[39]], None),
    ([40], None),
    ([pd.DataFrame()], None),
    ([{'a': 0}], None),
    ([pd.DataFrame()], None),
]

@pytest.mark.parametrize("x,raises", list_inp)
def test_elements_list(x, raises):
    list_ = List[MultiVal(3, '12'), {'_value_': [39]}, Value(40), dict, Type(pd.DataFrame)]
    #print(list_.to_dict())
    #print(MultiVal(3, '12').to_dict())
    _verify(list_, x, raises)
    

def test_NullDict():
    nd = NullDict[str]
    nd.verify({'a': None, 'b': 'X'})


def test_elements___call__():
    dtyct_ = Dtyct({'a': float, 'b': Type(str)}, defval={'a': 2, 'b': 'B'})
    d = dtyct_()
    assert d == {'a': 2, 'b': 'B'}
    d['b'] = 'X'
    dtyct_.verify(d)
