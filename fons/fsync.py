import os
import sys
from random import randint
import shutil
import zipfile
import time

LETTERS = ''.join(chr(i) for i in range(128) if chr(i).isalpha())

def random_nonce(length):
    select = [LETTERS[randint(0, len(LETTERS)-1)] for _ in range(length)]
    return ''.join(select)

ONEDRIVE_POTENTIAL_ROOTS = [
    'C:\\Users\\remil\\OneDrive',
    'D:\\OneDrive',
]
ONEDRIVE_ROOT = next(x for x in ONEDRIVE_POTENTIAL_ROOTS if os.path.exists(x))
#DONT_CHANGE = ['.preferences']
PATHS = {
    'PC_TEST': 'C:\\PProjects\\.test_updating',
    'ONEDRIVE_TEST': os.path.join(ONEDRIVE_ROOT, '.test_updating'),
    'ONEDRIVE_ZIP': os.path.join(ONEDRIVE_ROOT, '.test_updating.zip'),
    'PRODUCTION': 'C:\\PProjects\\PyProjects_test',
    'PC': 'C:\\PProjects\\PyProjects_dev',
    'ONEDRIVE': os.path.join(ONEDRIVE_ROOT, 'PyProjects_test'),
}
PATHS['DEV'] = PATHS['PC']
DONT_UPDATE_CONTENTS = \
    [PATHS['PC']+'\\crypi\\data\\cyInf',
     PATHS['PC']+'\\crypi\\data\\cmd\\__cache__',
     PATHS['ONEDRIVE_TEST']+'\\test_prj\\not_allowed_folder']
IGNORE_DIRS = ['__pycache__','.pytest_cache']
IGNORE_FILES = ['geckodriver.log', 'prj.yaml']

source = None
dest = None

def purge_walk(path):
    """os.walk path and remove all files&folders"""
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            os.remove(os.path.join(root, f))
        for d in dirs:
            os.rmdir(os.path.join(root, d))
    os.rmdir(path)


def force_delete(path):
    if os.path.isdir(path):
        os.system('cmd /c @RD /S /Q "{}"'.format(path))
    else:
        os.system('cmd /c del "{}" /F'.format(path))


def unpack(zip_path):
    zip_dir = os.path.dirname(zip_path)
    print('Unpacking {} to {}'.format(zip_path, zip_dir))
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(zip_dir)

def unpack2(zip_path):
    from fons.time import pydt
    """Preserves the last modified ts"""
    zip_dir = os.path.dirname(zip_path)
    print('Unpacking {} to {}'.format(zip_path, zip_dir))
    with zipfile.ZipFile(zip_path, 'r') as z:
        for f in z.infolist():
            rel_path, date_time = f.filename, f.date_time
            rel_path = rel_path.replace('/','\\')
            is_dir = rel_path.endswith('\\')
            path = os.path.join(zip_dir, rel_path)
            if is_dir:
                if not os.path.isdir(path):
                    os.mkdir(path)
            else:
                dir = os.path.dirname(path)
                if not os.path.isdir(dir):
                    os.mkdir(dir)
                with open(path, 'wb') as outFile:
                    outFile.write(z.open(f).read())
                # It seems to be a second behind
                date_time = time.mktime(date_time + (0, 0, -1)) + 1
                #print(rel_path)
                #print(date_time)
                #print(pydt(date_time).isoformat())
                os.utime(path, (date_time, date_time))


def is_allowed(path, is_dir=False):
    split = path.split('\\')[:(-1 if not is_dir else None)]
    return not any('\\'.join(split[:i+1]) in DONT_UPDATE_CONTENTS
                   for i in range(len(split)))


def already_added(path, dirs, is_dir=True):
    split = path.split('\\')[:(-1 if not is_dir else None)]
    return any('\\'.join(split[:i+1]) in dirs
               for i in range(len(split)))


def get_info(source_path, dest_path):
    #rn_path = os.path.join(dest_path, random_nonce(16))
    if not os.path.isdir(dest_path):
        os.mkdir(dest_path)
    #else:
    #    os.path.rename(dest_path, rn_path)
    len_source_path = len(source_path)
    len_dest_path = len(dest_path)
    info = []
    delete_dirs = []
    ignore_dirs = []

    def is_file_changed(path, path2):
        if not os.path.isfile(path2):
            return True

        if os.path.getsize(path) != os.path.getsize(path2):
            return True
        
        file_last_modified = os.path.getmtime(path)
        file2_last_modified = os.path.getmtime(path2)
        
        if file_last_modified != file2_last_modified:
            with open(path, 'rb') as f:
                bytes = f.read()
            with open(path2, 'rb') as f:
                bytes2 = f.read()
            #print(path, path2, 'contents match:', bytes==bytes2)
            return bytes != bytes2

        return False
    
    # CREATE
    for root, dirs, files in os.walk(source_path, topdown=True):
        rel_root = root[len_source_path+1:]
        source_root = root
        dest_root = os.path.join(dest_path, rel_root)
        parent_dir_names = rel_root.split('\\')
        if any(name in IGNORE_DIRS for name in parent_dir_names):
            if not already_added(root, ignore_dirs, is_dir=True):
                ignore_dirs.append(root)
            continue
        for dir in dirs:
            source_dir_path = os.path.join(source_root, dir)
            dest_dir_path = os.path.join(dest_root, dir)
            if dir in IGNORE_DIRS:
                info.append(('IGNORE','dir',source_dir_path,dest_dir_path))
                continue
            if not os.path.isdir(dest_dir_path):
                info.append(('MAKE','dir',source_dir_path,dest_dir_path))
        for f in files:
            source_file_path = os.path.join(source_root, f)
            dest_file_path = os.path.join(dest_root, f)
            if f in IGNORE_FILES:
                info.append(('IGNORE','file',source_dir_path,dest_dir_path))
                continue
            if is_allowed(dest_file_path, is_dir=False) and is_file_changed(source_file_path, dest_file_path):
                info.append(('MAKE','file',source_file_path,dest_file_path))
            else:
                info.append(('IGNORE','file',source_file_path,dest_file_path))

    # REMOVE
    for root, dirs, files in os.walk(dest_path, topdown=True):
        rel_root = root[len_dest_path+1:]
        source_root = os.path.join(source_path, rel_root)
        dest_root = root
        parent_dir_names = rel_root.split('\\')
        if any(name in IGNORE_DIRS for name in parent_dir_names):
            if not already_added(root, ignore_dirs, is_dir=True):
                ignore_dirs.append(root)
            continue
        for dir in dirs:
            dest_dir_path = os.path.join(dest_root, dir)
            source_dir_path = os.path.join(source_root, dir)
            if dir in IGNORE_DIRS:
                info.append(('IGNORE','dir',dest_dir_path,source_dir_path))
                continue
            if not os.path.isdir(source_dir_path) \
                   and not already_added(dest_dir_path, delete_dirs, is_dir=True):
                info.append(('DELETE','dir',source_dir_path,dest_dir_path))
                delete_dirs.append(dest_dir_path)
        for f in files:
            dest_file_path = os.path.join(dest_root, f)
            source_file_path = os.path.join(source_root, f)
            if f in IGNORE_FILES:
                info.append(('IGNORE','file',dest_file_path,source_file_path))
                continue
            if not os.path.isfile(source_file_path) \
                    and not already_added(dest_file_path, delete_dirs, is_dir=False):
                if is_allowed(dest_file_path, is_dir=False):
                    info.append(('DELETE','file',source_file_path,dest_file_path))
                else:
                    info.append(('IGNORE','file',dest_file_path,source_file_path))
    
    return info


def operate(item, show_ignore=True):
    op, type, source, dest = item
    print_strs = {
        'IGNORE': 'Ignoring',
        'MAKE': 'Creating',
        'DELETE': 'Removing'
    }
    path = dest if op!='IGNORE' else source
    print_str = op #print_strs[op]
    if op == 'MAKE' and os.path.isfile(path):
        print_str = 'UPDATE' #'Updating'
    add_str = '(f)' if type=='file' else '(d)'
    if op!='IGNORE' or show_ignore:
        print('{}{} {}'.format(print_str, add_str, path))
    if op == 'MAKE':
        if type == 'dir':
            os.mkdir(path)
        else:
            shutil.copy2(source, path)
    elif op == 'DELETE':
        if type == 'dir':
            try:
                shutil.rmtree(path)
            except PermissionError as e:
                print('rmtree on {} failed ({}). Attempting force delete.'.format(path, repr(e)))
                force_delete(path)
        else:
            try:
                os.remove(path)
            except PermissionError as e:
                print('os.remove on {} failed ({}). Attempting force delete.'.format(path, repr(e)))
                force_delete(path)


def update(source, dest, show_ignore=False):
    info = get_info(source, dest)
    for item in info:
        operate(item, show_ignore)


def main(argv=sys.argv):
    source = dest = None
    source_name = None
    _from = _to = None
    txt = '"from:" / "to:" + "onedrive" / "pc" / "production"|| "test"\n'
    
    while _from is None or _to is None or _from == _to:
        inp = input(txt)
        split = [x.strip() for x in inp.split(':')]
        if inp == 'test':
            _from = 'pc_test'
            _to = 'onedrive_test'
        elif len(split)!=2 or split[0] not in ('from','to')\
                 or split[1] not in ('onedrive','pc','production','dev'):
            print('Incorrect input!')
        elif split[0] == 'from':
            _from = split[1]
        else:
            _to = split[1]
        txt = ''
    
    source = PATHS[_from.upper()]
    dest = PATHS[_to.upper()]
    show_ignore = (_from == 'pc_test')
    if 'show_ignore' in argv:
        show_ignore = True
    
    if _to == 'onedrive_test':
        if os.path.isdir(PATHS['ONEDRIVE_TEST']):
            print('Removing old Onedrive test dir.')
            shutil.rmtree(PATHS['ONEDRIVE_TEST'])
        unpack2(PATHS['ONEDRIVE_ZIP'])
    
    projects = [x for x in os.listdir(source)
                if os.path.exists(os.path.join(source, x, '.project'))]
    
    for name in projects:
        print("----------------------------------------")
        print("Project: '{}'".format(name))
        update(os.path.join(source, name), os.path.join(dest, name), show_ignore)


if __name__ == '__main__':
    main()

