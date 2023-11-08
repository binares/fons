import pytest
from collections import OrderedDict as OD
import pandas as pd, numpy as np
import datetime as dt

td = dt.timedelta
import copy
import pprint as pp

import fons.verify_old as vfy


DNFO = {
    "tch": {
        "_type_": pd.DataFrame,
        "dtypes": OD(zip(["prc", "vol_b", "vol_s", "vol", "volC"], [float] * 5)),
    },
    "mh": {
        "_type_": pd.DataFrame,
        "dtypes": OD(
            [
                ["TimeStamp", "datetime64[ns]"],
                ["OrderType", str],
                ["Price", float],
                ["Quantity", float],
                ["Total", float],
                ["Id", int],
                ["FillType", str],
            ]
        ),
    },
    "obs": {"_type_": list},
    "pvhist": {
        "_type_": dict,
        "items": {
            "_prh": {"_type_": list, "unit": {"_type_": float}},
            "_vlh24": {"_type_": list},
            "_timestamps": {
                "_type_": dict,
                "items": {
                    "timestamps": {"_type_": list},
                    "new_timestamps": {"_type_": list},
                    "indexes": {"_type_": list},
                    "new_vol24stamps": {"_type_": list},
                },
            },
        },
    },
    "prc": {"_type_": float, "_defval_": np.nan},
    "vol24": {"_type_": float, "_defval_": np.nan},
    # }
    "news": {
        "_type_": pd.DataFrame,
        "data": OD(
            [
                ["TimeStamp", dt.datetime(2000, 1, 1)],
                ["TimeObtained", dt.datetime(2000, 1, 2)],
                ["TimeForwarded", dt.datetime(2000, 1, 3)],
                ["TimeForwarded2", dt.datetime(2000, 1, 14)],
                ["Id", 0],
                ["Source", "asource"],  #'Twitter' or 'Reddit'
                ["UserName", "auser"],
                ["UserId", "auserid"],
                ["InReplyTo", "ainreplyto"],  # user's screen name
                ["Text", "atext"],
                ["TextHighlighted", "atexthighlighted"],
                ["+", 0],
                ["-", 1],
                ["O", 2],
                ["Link", "alink"],
                ["RetweetCount", 3],
                ["FavoriteCount", 4],
                ["Mentions", "amentions"],
                ["Forward", True],
            ]
        ),
        "dtypes": OD(
            [
                ["TimeStamp", "datetime64[ns]"],
                ["TimeObtained", "datetime64[ns]"],
                ["TimeForwarded", "datetime64[ns]"],
                ["TimeForwarded2", "datetime64[ns]"],
                ["Id", str],
                ["Source", str],  #'Twitter' or 'Reddit'
                ["UserName", str],
                ["UserId", str],
                ["InReplyTo", str],  # user's screen name
                ["Text", str],
                ["TextHighlighted", str],
                ["+", int],
                ["-", int],
                ["O", int],
                ["Link", str],
                ["RetweetCount", int],
                ["FavoriteCount", int],
                ["Mentions", str],
                ["Forward", bool],
            ]
        ),
    },
    "signals": {
        "_type_": list,
        "unit": {
            "_type_": dict,
            "dtypes": OD(
                [
                    ["id", str],
                    ["uid", int],
                    ["market", str],
                    ["ts", dt.datetime],
                    [
                        "prc",
                        {
                            "_type_": dict,
                            "dtypes": OD(
                                [
                                    ["open", float],
                                    ["close", float],
                                    ["incr", float],
                                    ["cd", float],
                                    ["param_pos", int],
                                    ["incr24", float],
                                ]
                            ),
                        },
                    ],
                    [
                        "vol",
                        {
                            "_type_": dict,
                            "dtypes": OD(
                                [["vol", float], ["ratio", float], ["ratio24", float]]
                            ),
                        },
                    ],
                ]
            ),
        },
    },
    "X": {"_type_": "type", "_value_": "pd.DataFrame"},
    "Y": {"_type_": type, "_value_": list},
    "Z": {"_type_": "type", "_value_": "type"},
}


_unitTD = {"_type_": dt.timedelta, "_call_": None}
_unitDT = {"_type_": dt.datetime, "_call_": None}
_multiunit = {"_multi_": [_unitTD, _unitDT]}

tp_types = [
    {"_type_": tuple, "unit": _multiunit, "_call_": None},
    {"_type_": list, "unit": _multiunit, "_call_": None},
    _unitTD,
    _unitDT,
]

DNFO["tp"] = {"_defval_": None, "_multi_": tp_types}


MH = DNFO["mh"]
mh_dtps = DNFO["mh"]["dtypes"]
t_mh = pd.DataFrame(columns=mh_dtps.keys())
for c, dtype in mh_dtps.items():
    t_mh[c] = t_mh[c].astype(dtype)
t_mh2 = None


def test_isinstructions():
    assert vfy._isinstructions(MH)
    assert not vfy._isinstructions({"type": {"_type_": 2}})


def test_copy():
    global t_mh2
    t_mh2 = vfy._copy(t_mh)

    assert (t_mh == t_mh2).all().all()
    assert t_mh is not t_mh2


def test_normalise():
    norm = vfy.normalise(MH)
    assert DNFO["mh"]["columns"] == list(MH["dtypes"].keys())
    assert (MH["_copy_"] == t_mh).all().all()


def test_normalise_element():
    dflt = {"_type_": type(np.nan), "_value_": np.nan, "_isnorm_": True}

    assert vfy.normalise_element(2, default=np.nan) == {
        "_type_": int,
        "_value_": 2,
        "_defval_": dflt,
        "_isnorm_": True,
    }


def test_verify_data():
    t_mh3 = t_mh2.copy()
    t_mh3["TimeStamp"] = "2"
    with pytest.raises(TypeError) as e_info:
        vfy.verify_data(t_mh3, DNFO["mh"])

    t_mh3 = t_mh2.copy()
    t_mh3["E"] = np.nan
    with pytest.raises(KeyError) as e_info:
        vfy.verify_data(t_mh3, DNFO["mh"])

    MH2 = copy.deepcopy(DNFO["mh"])
    MH2["index"] = [33]
    t_mh3 = vfy.init_data(MH2)
    MH2["index"].append(44)

    with pytest.raises(KeyError) as e_info:
        vfy.verify_data(t_mh3, MH2)


S = s = None
SIG = DNFO["signals"]


def test_init_data():
    data = vfy.init_data(DNFO)
    for k, norm in DNFO.items():
        vfy.verify_data(data[k], norm)

    global S, s
    S = data["signals"]
    s = vfy.init_data(SIG["unit"])

    s["uid"] = 8
    s["prc"]["incr"] = 2.4
    S.append(s)

    # pp.pprint(s)
    # pp.pprint(SIG)

    vfy.verify_data(S, DNFO["signals"])


# More _verify data tests:
def test_verify_data2():
    s2 = vfy._copy(s)
    # s2['ts'] = #np.nan #None #4.8 #3453253245
    s2["ts"] = pd.Timestamp(dt.datetime(2000, 1, 1))
    S2 = S + [s2]
    # pp.pprint('S2: {}'.format(S2))

    s2["prc"]["incr"] = 2
    vfy.verify_data(S2, DNFO["signals"])

    s2["uid"] = 8.3
    with pytest.raises(TypeError) as e_info:
        vfy.verify_data(S2, DNFO["signals"])

    s3 = vfy._copy(s)
    s4 = vfy._copy(s)
    del s3["market"]
    s4["vol"]["extrakey"] = np.nan
    S3 = S + [s3]
    S4 = S + [s4]
    # pp.pprint('S3 {}'.format(S3))
    # pp.pprint('S4 {}'.format(S4))

    with pytest.raises(KeyError) as e_info:
        vfy.verify_data(S3, DNFO["signals"])

    with pytest.raises(KeyError) as e_info:
        vfy.verify_data(S4, DNFO["signals"])


def test_fill_missing():
    s5 = s.copy()
    del s5["ts"]
    del s5["prc"]

    s6 = vfy.fill_missing(s5, SIG["unit"])
    # pp.pprint(s5)
    # pp.pprint(s6)
    vfy.verify_data(s5, SIG["unit"])
    vfy.verify_data(s6, SIG["unit"])


atp1 = (dt.datetime(2000, 1, 4), dt.datetime(2000, 1, 6))
atp2 = (td(3), td(2))
atp3 = (atp1[0], atp2[1])
atp4 = (atp2[0], atp1[1])
atp5 = dt.datetime(2000, 1, 4)
atp6 = td(2)

atps_tuple = (atp1, atp2, atp3, atp4)
atps_list = tuple((list(x) for x in atps_tuple))
atps = atps_tuple + atps_list + (atp5, atp6)

"""pp.pprint(DNFO['tp'])
print("\n")
vfy.init_data(DNFO['tp'])
pp.pprint(DNFO['tp'])
input()"""


@pytest.mark.parametrize("test_input", atps)
def test_verify_data3(test_input):
    vfy.verify_data(test_input, DNFO["tp"])


atps2 = (np.datetime64(dt.datetime(2000, 1, 1)), np.timedelta64(td(2)), (None, td(2)))


@pytest.mark.parametrize("test_input", atps2)
def test_verify_data4(test_input):
    with pytest.raises(Exception) as e_info:
        vfy.verify_data(test_input, DNFO["tp"])
