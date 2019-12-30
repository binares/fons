import os
import re
import tempfile
import zipfile
import platform

import fons.log as _log

_PLATFORM = platform.system()

logger,logger2,tlogger,tloggers,tlogger0 = _log.get_standard_5(__name__)


def _is_relative(path):
    return ':' not in path


def _resolve(pth, envdir):
    pth = os.path.normpath(pth)
    
    if _is_relative(pth):
        pth = os.path.join(envdir, pth)
        
    pth = os.path.realpath(pth)
    
    return pth


def search_in_file(path, str, encoding='utf-8'):
    with open(path, encoding=encoding) as f:
        txt = f.read()
        
    if str in txt:
        return True
    
    return False


def search(root, str, filenames=True, contents=True):
    found = []

    def _search(x,y): return y in x

    if os.path.isfile(root):
        walkthrough = [(os.path.dirname(root),('',),(os.path.basename(root),))]
        filenames = False
    elif os.path.isdir(root):
        walkthrough = os.walk(root)
    else:
        raise FileNotFoundError('Root \'{}\' doesn\'t exist'.format(root))
        
    for _root,dirs,files in walkthrough:
        for fn in files:
            pth = os.path.join(_root,fn)
            
            if filenames and _search(fn,str):
                found.append(pth)
            elif contents:
                try: assert search_in_file(pth,str)
                except Exception: pass
                else: found.append(pth)

        if filenames:
            found += [os.path.join(root,x) for x in dirs if str in x]

    return found


def replace(root, str, replace_with):

    def _overwrite(path, new_contents):
        fd, temp_path = tempfile.mkstemp()
        bytes = new_contents.encode('utf-8')
        try:
            with os.fdopen(fd, 'wb') as tmp:
                tmp.write(bytes)
            os.remove(path)
            os.rename(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    
    def _replace(path):
        with open(path, encoding='utf-8') as f:
            contents = f.read()
            
        if str not in contents:
            return ''
        
        new_contents = re.sub(str, replace_with, contents)
        _overwrite(path, new_contents)
        
        return path
        
        
    if os.path.isfile(root):
        walkthrough = [(os.path.dirname(root),('',),(os.path.basename(root),))]
    elif os.path.isdir(root):
        walkthrough = os.walk(root)
    else:
        raise FileNotFoundError('Root \'{}\' doesn\'t exist'.format(root))
    
    replaced = []
    failed = []
        
    for _root,dirs,files in walkthrough:
        for fn in files:
            pth = os.path.join(_root,fn)
            try:
                if _replace(pth):
                    replaced.append(pth)
            except Exception:
                failed.append(pth)

    return replaced, failed


def delete_empty_dirs(root, recycler=None):
    ow = os.walk(root,topdown=False)
    
    for root,dirs,files in ow:
        
        for _dir in dirs:
            _dirpth = os.path.join(root,_dir)
            
            try: 
                if len(os.listdir(_dirpth)):
                    continue
            except FileNotFoundError:
                continue
            
            if recycler is not None:
                recycler(_dirpth)
                continue
            
            logger.debug('_dirpth_ removing: {}'.format(_dirpth))
            
            try: os.rmdir(_dirpth)
            except FileNotFoundError: pass
            except Exception as e:
                logger.exception(e)


def make_dirpath(*args):
    path = ''
    for a in args:
        path = os.path.join(path,a)
        if not os.path.isdir(path):
            os.mkdir(path)
    return path


def get_appdata_dir(appname, windows_select='Local', make=False):
    """https://stackoverflow.com/a/1088459/10492167"""
    if windows_select not in ['Local','LocalLow','Roaming']:
        raise ValueError(windows_select)
    
    if _PLATFORM == 'Darwin':
        from AppKit import NSSearchPathForDirectoriesInDomains
        # http://developer.apple.com/DOCUMENTATION/Cocoa/Reference/Foundation/Miscellaneous/Foundation_Functions/Reference/reference.html#//apple_ref/c/func/NSSearchPathForDirectoriesInDomains
        # NSApplicationSupportDirectory = 14
        # NSUserDomainMask = 1
        # True for expanding the tilde into a fully qualified path
        appdata = os.path.join(NSSearchPathForDirectoriesInDomains(14, 1, True)[0], appname)
    elif _PLATFORM == 'Windows':
        local = os.path.normpath(os.environ['APPDATA']+'/../{}'.format(windows_select))
        appdata = os.path.join(local, appname)
    else:
        appdata = os.path.expanduser(os.path.join("~", "." + appname))
    
    if make:
        make_dirpath(appdata)
        
    return appdata


def zip_contents(path, destination=None,
                 compression='ZIP_DEFLATED',
                 include_pycache=False,
                 exists='error'):
    
    """
    :param path: path or list of paths.
                 If a path is directory, all its contents will be zipped under
                 the name of the directory. Relative paths are assumed to be relative
                 to the parent directory of the first path in the list, and the first path
                 to the current working directory.
                 In case an outermost directory/file already exists in the in-the-making
                 zip file, the directory/file is renamed to "{original_base}({n}){original_suffix}"
                 (the suffix is for files only).
    
    :param exists: "error" or "rename"
                The action applies to `destination`.
    """
    
    if isinstance(compression,str):
        compression = getattr(zipfile, compression)
        
    if exists not in (None,'error','rename'):
        raise ValueError("`exists` must be either 'error' or 'rename'; got: {}".format(exists))
    
    paths = [path] if isinstance(path, str) else path
    paths[0] = main_path = os.path.realpath(paths[0])
    main_envdir = os.path.dirname(main_path)
    
    paths = [paths[0]] + [_resolve(pth, main_envdir) for pth in paths[1:]]
    
    if destination is None:
        destination = os.path.join(main_envdir, os.path.basename(main_path)+'.zip')
    
    destination = _resolve(destination, main_envdir)

    if exists in (None,'error') and os.path.exists(exists):
        raise OSError('Destination {} already exists'.format(destination))    

    i = 0
    has_zipend = destination.endswith('.zip')
    body = destination[:-4] if has_zipend else destination
    
    while os.path.exists(destination):
        destination = '{}({}){}'.format(body, i+2, '.zip' if has_zipend else '')
        i+=1
        
    cache = ('__pycache__', '.cache', '.pytest_cache')
    _contains_cache_dir = lambda tail: any(c in tail for c in cache)
    
    ignore = 'geckodriver.log'
    _filter = lambda files: [f for f in files if f not in ignore]
    
    zf = zipfile.ZipFile(destination, 'w', compression)
    
    
    def _rename(pth, is_file=False, zf_outermost_dirs=set(), zf_outermost_files=set()):
        name = os.path.basename(pth)
        
        if is_file and '.' in name:
            dot_loc = name.rfind('.')
            body, suffix = name[:dot_loc], name[dot_loc:]
        else:
            body, suffix = name, ''
        
        reg = zf_outermost_dirs if not is_file else zf_outermost_files  
        i = 0
        
        while name in reg:
            name = '{}({}){}'.format(body, i+2, suffix)
            i +=1
            
        reg.add(name)
        
        return os.path.join(os.path.dirname(pth), name)
    
    
    def _zip_directory(pth):
        len_pth = len(pth)
        len_split = len(os.sep)
                
        pth2 = _rename(pth)
        basedir = os.path.basename(pth2)
        
        for root, dirs, files in os.walk(pth):
            tail = root.split(os.sep)[len_split:]
            if include_pycache: pass
            elif _contains_cache_dir(tail): continue
            else: files = _filter(files)
            
            rel_path = os.path.join(basedir, root[len_pth+1:])
                
            for f in files:
                zf.write(os.path.join(root,f), os.path.join(rel_path, f))
    
    
    for pth in paths:
        if os.path.isdir(pth):
            _zip_directory(pth)
        else:
            pth2 = _rename(pth, is_file=True)
            zf.write(pth, os.path.basename(pth2))
 
    zf.close()


    return destination
