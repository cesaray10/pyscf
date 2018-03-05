#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
Some hacky functions
'''

import os, sys
import warnings
import imp
import tempfile
import shutil
import functools
import itertools
import math
import types
import ctypes
import numpy
import h5py
from pyscf.lib import param

if h5py.version.version[:4] == '2.2.':
    sys.stderr.write('h5py-%s is found in your environment. '
                     'h5py-%s has bug in threading mode.\n'
                     'Async-IO is disabled.\n' % ((h5py.version.version,)*2))

c_double_p = ctypes.POINTER(ctypes.c_double)
c_int_p = ctypes.POINTER(ctypes.c_int)
c_null_ptr = ctypes.POINTER(ctypes.c_void_p)

def load_library(libname):
# numpy 1.6 has bug in ctypeslib.load_library, see numpy/distutils/misc_util.py
    if '1.6' in numpy.__version__:
        if (sys.platform.startswith('linux') or
            sys.platform.startswith('gnukfreebsd')):
            so_ext = '.so'
        elif sys.platform.startswith('darwin'):
            so_ext = '.dylib'
        elif sys.platform.startswith('win'):
            so_ext = '.dll'
        else:
            raise OSError('Unknown platform')
        libname_so = libname + so_ext
        return ctypes.CDLL(os.path.join(os.path.dirname(__file__), libname_so))
    else:
        _loaderpath = os.path.dirname(__file__)
        return numpy.ctypeslib.load_library(libname, _loaderpath)

#Fixme, the standard resouce module gives wrong number when objects are released
#see http://fa.bianp.net/blog/2013/different-ways-to-get-memory-consumption-or-lessons-learned-from-memory_profiler/#fn:1
#or use slow functions as memory_profiler._get_memory did
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
PAGESIZE = os.sysconf("SC_PAGE_SIZE")
def current_memory():
    #import resource
    #return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000
    if sys.platform.startswith('linux'):
        with open("/proc/%s/statm" % os.getpid()) as f:
            vms, rss = [int(x)*PAGESIZE for x in f.readline().split()[:2]]
            return rss/1e6, vms/1e6
    else:
        return 0, 0

def num_threads(n=None):
    '''Set the number of OMP threads.  If argument is not given, the function
    will return the total number of available OMP threads.'''
    from pyscf.lib.numpy_helper import _np_helper
    if n is not None:
        _np_helper.set_omp_threads.restype = ctypes.c_int
        threads = _np_helper.set_omp_threads(ctypes.c_int(int(n)))
        if threads == 0:
            warnings.warn('OpenMP is not available. '
                          'Setting omp_threads to %s has no effects.' % n)
        return threads
    else:
        _np_helper.get_omp_threads.restype = ctypes.c_int
        return _np_helper.get_omp_threads()

class with_omp_threads(object):
    '''
    Usage:
        with lib.with_threads(2):
            print(lib.num_threads())
            ...
    '''
    def __init__(self, nthreads=None):
        self.nthreads = nthreads
        self.sys_threads = None
    def __enter__(self):
        if self.nthreads is not None and self.nthreads >= 1:
            self.sys_threads = num_threads()
            num_threads(self.nthreads)
        return self
    def __exit__(self, type, value, traceback):
        if self.sys_threads is not None:
            num_threads(self.sys_threads)


def c_int_arr(m):
    npm = numpy.array(m).flatten('C')
    arr = (ctypes.c_int * npm.size)(*npm)
    # cannot return LP_c_double class,
    #Xreturn npm.ctypes.data_as(c_int_p), which destructs npm before return
    return arr
def f_int_arr(m):
    npm = numpy.array(m).flatten('F')
    arr = (ctypes.c_int * npm.size)(*npm)
    return arr
def c_double_arr(m):
    npm = numpy.array(m).flatten('C')
    arr = (ctypes.c_double * npm.size)(*npm)
    return arr
def f_double_arr(m):
    npm = numpy.array(m).flatten('F')
    arr = (ctypes.c_double * npm.size)(*npm)
    return arr


def member(test, x, lst):
    for l in lst:
        if test(x, l):
            return True
    return False

def remove_dup(test, lst, from_end=False):
    if test is None:
        return set(lst)
    else:
        if from_end:
            lst = list(reversed(lst))
        seen = []
        for l in lst:
            if not member(test, l, seen):
                seen.append(l)
        return seen

def remove_if(test, lst):
    return [x for x in lst if not test(x)]

def find_if(test, lst):
    for l in lst:
        if test(l):
            return l
    raise ValueError('No element of the given list matches the test condition.')

def arg_first_match(test, lst):
    for i,x in enumerate(lst):
        if test(x):
            return i
    raise ValueError('No element of the given list matches the test condition.')

def _balanced_partition(cum, ntasks):
    segsize = float(cum[-1]) / ntasks
    bounds = numpy.arange(ntasks+1) * segsize
    displs = abs(bounds[:,None] - cum).argmin(axis=1)
    return displs

def _blocksize_partition(cum, blocksize):
    n = len(cum) - 1
    displs = [0]
    if n == 0:
        return displs

    p0 = 0
    for i in range(1, n):
        if cum[i+1]-cum[p0] > blocksize:
            displs.append(i)
            p0 = i
    displs.append(n)
    return displs

def flatten(lst):
    '''flatten nested lists
    x[0] + x[1] + x[2] + ...

    Examples:

    >>> flatten([[0, 2], [1], [[9, 8, 7]]])
    [0, 2, 1, [9, 8, 7]]
    '''
    return list(itertools.chain.from_iterable(lst))

def prange(start, end, step):
    for i in range(start, end, step):
        yield i, min(i+step, end)

def prange_tril(start, stop, blocksize):
    '''for p0, p1 in prange_tril: p1*(p1+1)/2-p0*(p0+1)/2 < blocksize'''
    if start >= stop:
        return []
    idx = numpy.arange(start, stop+1)
    cum_costs = idx*(idx+1)//2 - start*(start+1)//2
    displs = [x+start for x in _blocksize_partition(cum_costs, blocksize)]
    return zip(displs[:-1], displs[1:])

def square_mat_in_trilu_indices(n):
    '''Return a n x n symmetric index matrix, in which the elements are the
    indices of the unique elements of a tril vector 
    [0 1 3 ... ]
    [1 2 4 ... ]
    [3 4 5 ... ]
    [...       ]
    '''
    idx = numpy.tril_indices(n)
    tril2sq = numpy.zeros((n,n), dtype=int)
    tril2sq[idx[0],idx[1]] = tril2sq[idx[1],idx[0]] = numpy.arange(n*(n+1)//2)
    return tril2sq

class ctypes_stdout(object):
    '''make c-printf output to string, but keep python print in /dev/pts/1.
    Note it cannot correctly handle c-printf with GCC, don't know why.
    Usage:
        with ctypes_stdout() as stdout:
            ...
        print(stdout.read())
    '''
    def __enter__(self):
        sys.stdout.flush()
        self._contents = None
        self.old_stdout_fileno = sys.stdout.fileno()
        self.bak_stdout_fd = os.dup(self.old_stdout_fileno)
        self.bak_stdout = sys.stdout
        self.fd, self.ftmp = tempfile.mkstemp(dir='/dev/shm')
        os.dup2(self.fd, self.old_stdout_fileno)
        sys.stdout = os.fdopen(self.bak_stdout_fd, 'w')
        return self
    def __exit__(self, type, value, traceback):
        sys.stdout.flush()
        os.fsync(self.fd)
        self._contents = open(self.ftmp, 'r').read()
        os.dup2(self.bak_stdout_fd, self.old_stdout_fileno)
        sys.stdout = self.bak_stdout # self.bak_stdout_fd is closed
        #os.close(self.fd) is closed when os.fdopen is closed
        os.remove(self.ftmp)
    def read(self):
        if self._contents:
            return self._contents
        else:
            sys.stdout.flush()
            #f = os.fdopen(self.fd, 'r') # need to rewind(0) before reading
            #f.seek(0)
            return open(self.ftmp, 'r').read()

class capture_stdout(object):
    '''redirect all stdout (c printf & python print) into a string
    Usage:
        with capture_stdout() as stdout:
            ...
        print(stdout.read())
    '''
    def __enter__(self):
        sys.stdout.flush()
        self._contents = None
        self.old_stdout_fileno = sys.stdout.fileno()
        self.bak_stdout_fd = os.dup(self.old_stdout_fileno)
        self.fd, self.ftmp = tempfile.mkstemp(dir='/dev/shm')
        os.dup2(self.fd, self.old_stdout_fileno)
        return self
    def __exit__(self, type, value, traceback):
        sys.stdout.flush()
        self._contents = open(self.ftmp, 'r').read()
        os.dup2(self.bak_stdout_fd, self.old_stdout_fileno)
        os.close(self.bak_stdout_fd)
        #os.close(self.fd) will be closed when os.fdopen is closed
        os.remove(self.ftmp)
    def read(self):
        if self._contents:
            return self._contents
        else:
            sys.stdout.flush()
            #f = os.fdopen(self.fd, 'r') # need to rewind(0) before reading
            #f.seek(0)
            return open(self.ftmp, 'r').read()

class quite_run(object):
    '''output nothing

    Examples
    --------
    with quite_run():
        ...
    '''
    def __enter__(self):
        sys.stdout.flush()
        self.dirnow = os.getcwd()
        self.tmpdir = tempfile.mkdtemp(dir='/dev/shm')
        os.chdir(self.tmpdir)
        self.old_stdout_fileno = sys.stdout.fileno()
        self.bak_stdout_fd = os.dup(self.old_stdout_fileno)
        self.fnull = open(os.devnull, 'wb')
        os.dup2(self.fnull.fileno(), self.old_stdout_fileno)
    def __exit__(self, type, value, traceback):
        sys.stdout.flush()
        os.dup2(self.bak_stdout_fd, self.old_stdout_fileno)
        self.fnull.close()
        shutil.rmtree(self.tmpdir)
        os.chdir(self.dirnow)


# from pygeocoder
# this decorator lets me use methods as both static and instance methods
# In contrast to classmethod, when obj.function() is called, the first
# argument is obj in omnimethod rather than obj.__class__ in classmethod
class omnimethod(object):
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        return functools.partial(self.func, instance)


class StreamObject(object):
    '''For most methods, there are three stream functions to pipe computing stream:

    1 ``.set_`` function to update object attributes, eg
    ``mf = scf.RHF(mol).set(conv_tol=1e-5)`` is identical to proceed in two steps
    ``mf = scf.RHF(mol); mf.conv_tol=1e-5``

    2 ``.run`` function to execute the kenerl function (the function arguments
    are passed to kernel function).  If keyword arguments is given, it will first
    call ``.set`` function to update object attributes then execute the kernel
    function.  Eg
    ``mf = scf.RHF(mol).run(dm_init, conv_tol=1e-5)`` is identical to three steps
    ``mf = scf.RHF(mol); mf.conv_tol=1e-5; mf.kernel(dm_init)``

    3 ``.apply`` function to apply the given function/class to the current object
    (function arguments and keyword arguments are passed to the given function).
    Eg
    ``mol.apply(scf.RHF).run().apply(mcscf.CASSCF, 6, 4, frozen=4)`` is identical to
    ``mf = scf.RHF(mol); mf.kernel(); mcscf.CASSCF(mf, 6, 4, frozen=4)``
    '''

    verbose = 0
    stdout = sys.stdout
    _keys = set(['verbose', 'stdout'])

    def kernel(self, *args, **kwargs):
        '''
        Kernel function is the main driver of a method.  Every method should
        define the kernel function as the entry of the calculation.  Note the
        return value of kernel function is not strictly defined.  It can be 
        anything related to the method (such as the energy, the wave-function,
        the DFT mesh grids etc.).
        '''
        pass

    def pre_kernel(self, envs):
        '''
        A hook to be run before the main body of kernel function is executed.
        Internal variables are exposed to pre_kernel through the "envs"
        dictionary.  Return value of pre_kernel function is not required.
        '''
        pass

    def post_kernel(self, envs):
        '''
        A hook to be run after the main body of the kernel function.  Internal
        variables are exposed to post_kernel through the "envs" dictionary.
        Return value of post_kernel function is not required.
        '''
        pass

    def run(self, *args, **kwargs):
        '''
        Call the kernel function of current object.  `args` will be passed
        to kernel function.  `kwargs` will be used to update the attributes of
        current object.  The return value of method run is the object itself.
        This allows a series of functions/methods to be executed in pipe.
        '''
        self.set(**kwargs)
        self.kernel(*args)
        return self

    def set(self, **kwargs):
        '''
        Update the attributes of the current object.  The return value of
        method set is the object itself.  This allows a series of
        functions/methods to be executed in pipe.
        '''
        #if hasattr(self, '_keys'):
        #    for k,v in kwargs.items():
        #        setattr(self, k, v)
        #        if k not in self._keys:
        #            sys.stderr.write('Warning: %s does not have attribute %s\n'
        #                             % (self.__class__, k))
        #else:
        for k,v in kwargs.items():
            setattr(self, k, v)
        return self

    def apply(self, fn, *args, **kwargs):
        '''
        Apply the fn to rest arguments:  return fn(*args, **kwargs).  The
        return value of method set is the object itself.  This allows a series
        of functions/methods to be executed in pipe.
        '''
        return fn(self, *args, **kwargs)

#    def _format_args(self, args, kwargs, kernel_kw_lst):
#        args1 = [kwargs.pop(k, v) for k, v in kernel_kw_lst]
#        return args + args1[len(args):], kwargs

    def check_sanity(self):
        '''
        Check input of class/object attributes, check whether a class method is
        overwritten.  It does not check the attributes which are prefixed with
        "_".  The
        return value of method set is the object itself.  This allows a series
        of functions/methods to be executed in pipe.
        '''
        if (self.verbose > 0 and  # logger.QUIET
            hasattr(self, '_keys')):
            check_sanity(self, self._keys, self.stdout)
        return self

_warn_once_registry = {}
def check_sanity(obj, keysref, stdout=sys.stdout):
    '''Check misinput of class attributes, check whether a class method is
    overwritten.  It does not check the attributes which are prefixed with
    "_".
    '''
    objkeys = [x for x in obj.__dict__ if not x.startswith('_')]
    keysub = set(objkeys) - set(keysref)
    if keysub:
        class_attr = set(dir(obj.__class__))
        keyin = keysub.intersection(class_attr)
        if keyin:
            msg = ('Overwritten attributes  %s  of %s\n' %
                   (' '.join(keyin), obj.__class__))
            if msg not in _warn_once_registry:
                _warn_once_registry[msg] = 1
                sys.stderr.write(msg)
                if stdout is not sys.stdout:
                    stdout.write(msg)
        keydiff = keysub - class_attr
        if keydiff:
            msg = ('%s does not have attributes  %s\n' %
                   (obj.__class__, ' '.join(keydiff)))
            if msg not in _warn_once_registry:
                _warn_once_registry[msg] = 1
                sys.stderr.write(msg)
                if stdout is not sys.stdout:
                    stdout.write(msg)
    return obj

def with_doc(doc):
    '''Use this decorator to add doc string for function

        @with_doc(doc)
        def fn:
            ...

    makes

        fn.__doc__ = doc
    '''
    def make_fn(fn):
        fn.__doc__ = doc
        return fn
    return make_fn

def import_as_method(fn, default_keys=None):
    '''
    The statement "fn1 = import_as_method(fn, default_keys=['a','b'])"
    in a class is equivalent to define the following method in the class:

    .. code-block:: python
        def fn1(self, ..., a=None, b=None, ...):
            if a is None: a = self.a
            if b is None: b = self.b
            return fn(..., a, b, ...)
    '''
    code_obj = fn.__code__
# Add the default_keys as kwargs in CodeType is very complicated
#    new_code_obj = types.CodeType(code_obj.co_argcount+1,
#                                  code_obj.co_nlocals,
#                                  code_obj.co_stacksize,
#                                  code_obj.co_flags,
#                                  code_obj.co_code,
#                                  code_obj.co_consts,
#                                  code_obj.co_names,
## As a class method, the first argument should be self
#                                  ('self',) + code_obj.co_varnames,
#                                  code_obj.co_filename,
#                                  code_obj.co_name,
#                                  code_obj.co_firstlineno,
#                                  code_obj.co_lnotab,
#                                  code_obj.co_freevars,
#                                  code_obj.co_cellvars)
#    clsmethod = types.FunctionType(new_code_obj, fn.__globals__)
#    clsmethod.__defaults__ = fn.__defaults__

    # exec is a bad solution here.  But I didn't find a better way to
    # implement this for now.
    nargs = code_obj.co_argcount
    argnames = code_obj.co_varnames[:nargs]
    defaults = fn.__defaults__
    new_code_str = 'def clsmethod(self, %s):\n' % (', '.join(argnames))
    if default_keys is not None:
        for k in default_keys:
            new_code_str += '    if %s is None: %s = self.%s\n' % (k, k, k)
        if defaults is None:
            defaults = (None,) * nargs
        else:
            defaults = (None,) * (nargs-len(defaults)) + defaults
    new_code_str += '    return %s(%s)\n' % (fn.__name__, ', '.join(argnames))
    exec(new_code_str, fn.__globals__, locals())

    clsmethod.__name__ = fn.__name__
    clsmethod.__defaults__ = defaults
    return clsmethod

def overwrite_mro(obj, mro):
    '''A hacky function to overwrite the __mro__ attribute'''
    class HackMRO(type):
        pass
# Overwrite type.mro function so that Temp class can use the given mro
    HackMRO.mro = lambda self: mro
    #if sys.version_info < (3,):
    #    class Temp(obj.__class__):
    #        __metaclass__ = HackMRO
    #else:
    #    class Temp(obj.__class__, metaclass=HackMRO):
    #        pass
    Temp = HackMRO(obj.__class__.__name__, obj.__class__.__bases__, obj.__dict__)
    obj = Temp()
# Delete mro function otherwise all subclass of Temp are not able to
# resolve the right mro
    del(HackMRO.mro)
    return obj

def izip(*args):
    '''python2 izip == python3 zip'''
    if sys.version_info < (3,):
        return itertools.izip(*args)
    else:
        return zip(*args)

from threading import Thread
from multiprocessing import Queue, Process
class ProcessWithReturnValue(Process):
    def __init__(self, group=None, target=None, name=None, args=(),
                 kwargs=None):
        self._q = Queue()
        def qwrap(*args, **kwargs):
            self._q.put(target(*args, **kwargs))
        Process.__init__(self, group, qwrap, name, args, kwargs)
    def join(self):
        Process.join(self)
        try:
            return self._q.get(block=False)
        except:  # Queue.Empty error
            raise RuntimeError('Error on process %s' % self)
    get = join

class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None, args=(),
                 kwargs=None):
        self._q = Queue()
        def qwrap(*args, **kwargs):
            self._q.put(target(*args, **kwargs))
        Thread.__init__(self, group, qwrap, name, args, kwargs)
    def join(self):
        Thread.join(self)
        try:
            return self._q.get(block=False)
        except:  # Queue.Empty error
            raise RuntimeError('Error on thread %s' % self)
    get = join

def background_thread(func, *args, **kwargs):
    '''applying function in background'''
    thread = ThreadWithReturnValue(target=func, args=args, kwargs=kwargs)
    thread.start()
    return thread

def background_process(func, *args, **kwargs):
    '''applying function in background'''
    thread = ProcessWithReturnValue(target=func, args=args, kwargs=kwargs)
    thread.start()
    return thread

bg = background = bg_thread = background_thread
bp = bg_process = background_process


class H5TmpFile(h5py.File):
    def __init__(self, filename=None, *args, **kwargs):
        if filename is None:
            tmpfile = tempfile.NamedTemporaryFile(dir=param.TMPDIR)
            filename = tmpfile.name
        h5py.File.__init__(self, filename, *args, **kwargs)
    def __del__(self):
        self.close()

def finger(a):
    a = numpy.asarray(a)
    return numpy.dot(numpy.cos(numpy.arange(a.size)), a.ravel())


def ndpointer(*args, **kwargs):
    base = numpy.ctypeslib.ndpointer(*args, **kwargs)

    @classmethod
    def from_param(cls, obj):
        if obj is None:
            return obj
        return base.from_param(obj)
    return type(base.__name__, (base,), {'from_param': from_param})


class call_in_background(object):
    '''Asynchonously execute the given function

    Usage:
        with call_in_background(fun) as async_fun:
            async_fun(a, b)  # == fun(a, b)
            do_something_else()

        with call_in_background(fun1, fun2) as (afun1, afun2):
            afun2(a, b)
            do_something_else()
            afun2(a, b)
            do_something_else()
            afun1(a, b)
            do_something_else()
    '''
    def __init__(self, *fns):
        self.fns = fns
        self.handler = None

    def __enter__(self):
        if imp.lock_held():
# Some modules like nosetests, coverage etc
#   python -m unittest test_xxx.py  or  nosetests test_xxx.py
# hang when Python multi-threading was used in the import stage due to (Python
# import lock) bug in the threading module.  See also
# https://github.com/paramiko/paramiko/issues/104
# https://docs.python.org/2/library/threading.html#importing-in-threaded-code
# Disable the asynchoronous mode for safe importing
            def def_async_fn(fn):
                return fn

        elif h5py.version.version[:4] == '2.2.':
# h5py-2.2.* has bug in threading mode.
            def def_async_fn(fn):
                return fn

        else:
            def def_async_fn(fn):
                def async_fn(*args, **kwargs):
                    if self.handler is not None:
                        self.handler.join()
                    self.handler = Thread(target=fn, args=args, kwargs=kwargs)
                    self.handler.start()
                    return self.handler
                return async_fn

        if len(self.fns) == 1:
            return def_async_fn(self.fns[0])
        else:
            return [def_async_fn(fn) for fn in self.fns]

    def __exit__(self, type, value, traceback):
        if self.handler is not None:
            self.handler.join()


# A tag to label the derived Scanner class
class SinglePointScanner: pass
class GradScanner: pass


if __name__ == '__main__':
    for i,j in prange_tril(0, 90, 300):
        print(i, j, j*(j+1)//2-i*(i+1)//2)
