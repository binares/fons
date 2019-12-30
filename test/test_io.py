import os
from shutil import copy2
import pytest
import datetime
dt = datetime.datetime

import fons.io as io

fdir = os.path.dirname(__file__)
PARAMS_PATH = os.path.join(fdir, 'test_io_read_params.txt')
PARAMS_SAVE_PATH = os.path.join(fdir, 'test_io_read_params_out.txt')
_SETTINGS_PATH = os.path.join(fdir, 'test_io_update_settings.yaml')
SETTINGS_PATH = os.path.join(fdir, 'test_io_update_settings_COPY.yaml')
_SETTINGS_TEST3_PATH = os.path.join(fdir, 'test_io_update_settings_TEST3.yaml')
SETTINGS_TEST3_PATH = os.path.join(fdir, 'test_io_update_settings_TEST3_COPY.yaml')
SETTINGS_NO_INDENT_PATH = os.path.join(fdir, 'test_io_update_settings_no_indent.yaml')

#Copy the files, for eGit purposes 
#(if we don't copy and just overwrite the original, it thinks they've been updated)
copy2(_SETTINGS_PATH, SETTINGS_PATH)
copy2(_SETTINGS_TEST3_PATH, SETTINGS_TEST3_PATH)

p_expected = {
    'token': "jrhyyiycfev:j4vjxh7p06wsf1061wukwvjs3hnhm8",
    'contacts': {"self": 8711851293646172144751, "rndm": 234},
    'atpl': [False, True, True, False],
    2: ["sth", "other"],
    '2': ["sth", "other2"],
    None: ["sth", "other"],
    'end': "//",
    '<>': 2.4,
    'NEW_PARAM': ["a", "list"],
    'NEW_PARAM2': {"its k": "its v"},
    '613524184:xxpOiJ683r6iNvbCtgA2J4QD817FSTnfP': {"its k": "its v"},
}

def test_read_params():
    p = io.read_params(PARAMS_PATH)
    
    for k,v_expected in p_expected.items():
        assert p[k] == v_expected
    

def test_read_params_with_keys():
    p = io.read_params(PARAMS_PATH, ['token'])
    
    assert isinstance(p, dict) and len(p) == 1
    assert p['token'] == p_expected['token']
    

def test_read_params_raises_KeyError():
    with pytest.raises(KeyError):
        io.read_params(PARAMS_PATH, ['notPresentKey'])


def test_save_params():
    now = dt.utcnow().isoformat()
    
    io.save_params(PARAMS_SAVE_PATH, {'newKey': now}, read_path=PARAMS_PATH)
    
    p = io.read_params(PARAMS_SAVE_PATH)
    
    assert p['newKey'] == now
    
    for k,v_expected in p_expected.items():
        assert p[k] == v_expected
    
    os.remove(PARAMS_SAVE_PATH)
        

#---------------------------

_ijh = {'_type_': dict,
        'dtypes': {'k': {'_type_':dict,
                         'dtypes':{'l': str,
                                   'm': str}}}}
verify = {
    '_type_': dict,
    #'default_dtype': None
    'dtypes': {
        'abc': str,
        'edf': bool,
        'ijh': _ijh,
        'opq': int}}


def D():
    return {'abc': 'not_defined_yet'}

def _drop_meta(d):
    return {k: v for k,v in d.items() if k != '__meta__'}

def _get(config=None, verify=verify, deep=None, force_update=None):
    return [config, verify, deep, force_update]

#init verify deep force_update
_default = [True, verify, True, False]


expected_dicts = [
    {'abc': 'abcvalue', 'edf': True, 'ijh': {"k": {"l": None}}, 'opq': 1}, #0
    {'abc': 'test_abcvalue', 'edf': False, 'ijh': {"k": {"l": "lV", "m": "mV"}}, 'opq': 1}, #1 
    {'abc': None, 'opq': 2}, #2
    {'abc': 'test3_abcvalue', 'ijh': {'k': {'m': 't3mV'}}}, #3
    {'abc': 'test3_abcvalue', 'ijh': {'k': {'m': 't3mV'}}}, #4
]

_inp = [
    [D(), 'default']    + _default,
    [D(), 'TEST'] + _default,
    [D(), 'TEST2'] + _default,
    [D(), 'TEST3'] + [True, verify, False, False], #deep=False
    [D(), None] + [True, verify, False, False], #deep=False __config__ == TEST3
]

inp = [x[:1] + [expected_dicts[i]] + x[1:] for i,x in enumerate(_inp)]


@pytest.mark.parametrize("d,expected,config,init,verify,deep,force_update", inp)
def test_update_settings(d, expected, config, init, verify, deep, force_update):
    
    io.update_settings(SETTINGS_PATH, d, config=config, init=init,
                       verify=verify, deep=deep, force_update=force_update)
    
    assert _drop_meta(d) == expected
    

def test_update_settings_no_indent():
    d = {}
    io.update_settings(SETTINGS_NO_INDENT_PATH, d, config='TEST',
                       init=True, verify=verify, deep=True)
    assert d['__meta__']['default'] == None
    assert d['__meta__']['config'] == 'TEST'
    assert d['__meta__']['exclude'] == ['TEST','TEST2','TEST3']
    
    assert _drop_meta(d) == expected_dicts[1]
    

def test_update_settings_modified_time():
    
    def _update(d, force_update=False):
        io.update_settings(SETTINGS_PATH, d, config='TEST3', init=True,
                           verify=verify, deep=False, force_update=force_update)
        
    def _modify_file(path):
        temp_path = os.path.join(os.path.dirname(path), 'io_temp')
        with open(path) as f:
            with open(temp_path,'w') as f2:
                f2.write(f.read())
        os.remove(path)
        os.rename(temp_path, path)
        
    def _keep_only_meta(d):
        for k in list(d.keys()):
            if k != '__meta__':
                del d[k]
        #to force it to update the values
        if '__meta__' in d:
            d['__meta__']['last_input'] = {}
            d['__meta__']['last_input_meta'] = {}
                
    _get_dict = lambda d: dict(__meta__=d['__meta__'])
    
    def _verify(d, path):
        #add "modified" times to meta (if not already added)
        _keep_only_meta(d)
        _update(d)
        _keep_only_meta(d)
        
        #will not update the dict as the file hasn't been modified in the meanwhile
        _update(d)
        
        #values weren't updated
        assert list(d.keys()) == ['__meta__']
        
        #force update
        _update(d, True)
        
        #keys were added
        assert len(d) > 1
        
        #modify the file
        _modify_file(path)
        
        _keep_only_meta(d)
        
        #should update
        _update(d)
        
        #keys were added
        assert len(d) > 1
    
    d = {}
    
    _verify(d, SETTINGS_PATH)
    _verify(d, SETTINGS_TEST3_PATH)