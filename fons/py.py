from types import ModuleType
from importlib import reload
import os, sys


def mro(*bases):
    """Calculate the Method Resolution Order of bases using the C3 algorithm.

    Suppose you intended creating a class K with the given base classes. This
    function returns the MRO which K would have, *excluding* K itself (since
    it doesn't yet exist), as if you had actually created the class.

    Another way of looking at this, if you pass a single class K, this will
    return the linearization of K (the MRO of K, *including* itself).
    """
    seqs = [list(C.__mro__) for C in bases] + [list(bases)]
    res = []
    while True:
        non_empty = list(filter(None, seqs))
        if not non_empty:
            # Nothing left to process, we're done.
            return tuple(res)
        for seq in non_empty:  # Find merge candidates among seq heads.
            candidate = seq[0]
            not_head = [s for s in non_empty if candidate in s[1:]]
            if not_head:
                # Reject the candidate.
                candidate = None
            else:
                break
        if not candidate:
            raise TypeError("inconsistent hierarchy, no C3 MRO is possible")
        res.append(candidate)
        for seq in non_empty:
            # Remove candidate.
            if seq[0] == candidate:
                del seq[0]

    return res


def rreload2(module, seen=None):
    """Recursively reload modules."""
    if seen is None:
        seen = []
    if module in seen:
        return

    reload(module)
    seen.append(module)

    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)
        if type(attribute) is ModuleType:
            rreload2(attribute, seen)


def rreload(module, paths=None, mdict=None):
    """Recursively reload modules."""
    if paths is None:
        paths = [""]
    if mdict is None:
        mdict = {}
    if module not in mdict:
        # modules reloaded from this module
        mdict[module] = []
    reload(module)
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)
        if type(attribute) is ModuleType:
            if attribute not in mdict[module]:
                if attribute.__name__ not in sys.builtin_module_names:
                    if os.path.dirname(attribute.__file__) in paths:
                        mdict[module].append(attribute)
                        rreload(attribute, paths, mdict)
    reload(module)
    # return mdict


if __name__ == "__main__":

    class A:
        pass

    class B(A):
        pass

    class C(B):
        pass

    class D(B):
        pass

    class E(C, D):
        pass

    print(mro(C, D))
    print(E.__mro__[1:])
    # print(object.__dict__)
