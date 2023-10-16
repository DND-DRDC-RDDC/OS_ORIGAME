# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Asynchronously call methods from backend thread

Enables the GUI (frontend) to asynchronously call functions (any callable) from the backend thread,
and to receive the return values asynchronously into main thread. Application need only call
AsyncRequest.set_target_thread() once, and optionally set_error_handler(), in order to call
AsyncRequest.call() as many times as desired.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import traceback
import inspect
from collections import deque

# [2. third-party]
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

# [3. local]
from ..core import override, override_required
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..core.typing import AnnotationDeclarations
from .constants import BACKEND_THREAD_OBJECT_NAME

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'AsyncRequest',
    'IAsyncErrorHandler',
    'SimpleAsyncErrorHandler',
    'AsyncErrorInfo',
    'async_call_needed',
]

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    AsyncErrorInfo = 'AsyncErrorInfo'


ResponseCB = Callable[..., None]
AsyncRequestErrorCallable = Callable[[Decl.AsyncErrorInfo], None]


# -- Function definitions -----------------------------------------------------------------------


def async_call_needed(func: Callable) -> Callable:
    """
    Decorator that can be used to enforce the given function's thread affinity with the backend thread.

    Note: Apply it to the GUI variant functions that need backend access by AsyncRequest.call().
    :param func: The function that needs AsyncRequest.call()
    :return: The wrapper of the func. The wrapper does not change the func.
    """

    def wrapper(*args, **kwargs):
        current_thread_name = QThread.currentThread().objectName()
        if current_thread_name == BACKEND_THREAD_OBJECT_NAME:
            return func(*args, **kwargs)

        raise RuntimeError('This function "{}" must be run with an async call.'.format(func))

    return wrapper


# -- Class Definitions --------------------------------------------------------------------------

class AsyncErrorInfo:
    """
    Contains all the information needed for the error_cb callback to determine what error occurred in
    an asynchronous call.
    """

    def __init__(self, exc: BaseException, callable_obj: Callable, response_cb: ResponseCB):
        self.traceback = traceback.format_exc()
        # sometimes str(exc) is empty (like for assertions, or exceptions without text), in that case use traceback:
        self.msg = str(exc) or self.traceback
        self.exc = exc
        self.call_obj = callable_obj
        self.response_cb = response_cb


class IAsyncErrorHandler:
    """
    Interface class for the error handler given to AsyncRequest.set_global_error_handler(). The handler must
    provide two methods: one that will get called by the main thread when the function called by the backend
    thread raises an exception; the other when the response_cb raises an exception.
    """

    @override_required
    def on_call_error(self, exc_info: AsyncErrorInfo):
        """
        Called when the function called in backend thread raised an exception.
        :param exc: the exception object that was raised
        """
        raise NotImplementedError('IAsyncErrorHandler.on_call_error() function mandatory override not implemented.')

    @override_required
    def on_response_cb_error(self, exc_info: AsyncErrorInfo):
        """
        Called when the *response* function called in main thread raises an exception.
        :param exc: the exception object that was raised
        """
        raise NotImplementedError(
            'IAsyncErrorHandler.on_response_cb_error() function mandatory override not implemented.')


class AsyncRequester(QObject):
    """
    Connects to an instance of AsyncRequestHandler, which is then moved to the backend thread. The asynchronous
    connection to AsyncRequestHandler allows the requester to receive the response sent from the backend thread
    by the AsyncRequestHandler.

    The requester.sig_request_async is emitted with the following arguments:

    - callable_obj: any callable, to be called from backend thread
    - args: tuple, the position args to give to callable_obj
    - kwargs: dict, the kwargs to give to callable_obj
    - response_cb: any callable, to be called from main thread; it signature must be compatible with
        return value from callable_obj
    - error_cb: any callable that takes one argument, an instance of AsyncErrorInfo
    """

    sig_request_async = pyqtSignal(int)

    def __init__(self, backend_thread: QThread):
        super().__init__()
        self.req_handler = AsyncRequestHandler()
        self.req_handler.moveToThread(backend_thread)
        self.__previous_req_handler = None

        self.sig_request_async.connect(self.req_handler.accept_request)
        self.req_handler.sig_respond_async.connect(self.accept_response)

        self._global_error_handler = None

    def reset(self, backend_thread: QThread):
        """Reset this requester to use a req_handler for a different thread"""
        self.sig_request_async.disconnect(self.req_handler.accept_request)
        self.req_handler.sig_respond_async.disconnect(self.accept_response)
        self.req_handler.deleteLater()
        self.__previous_req_handler = self.req_handler

        self.req_handler = AsyncRequestHandler()
        self.req_handler.moveToThread(backend_thread)
        self.sig_request_async.connect(self.req_handler.accept_request)
        self.req_handler.sig_respond_async.connect(self.accept_response)

    def set_global_error_handler(self, handler):
        """When there is error in the req_handler or in the response callback, use the given handler."""
        self._global_error_handler = handler
        self.req_handler.global_error_handler = handler

    def queue_request(self, call_info: Tuple):
        call_id = self.req_handler.next_call_id
        self.req_handler.next_call_id += 1
        call_info = (call_id,) + call_info
        self.req_handler.call_queue.append(call_info)
        self.sig_request_async.emit(call_info[0])

    @pyqtSlot(int)
    def accept_response(self, expect_response_id: int):
        """Asynchronously receives the response from backend req_handler."""
        if not self.req_handler.response_queue:
            # Likely, the req_handler has been replaced by a new one, so we don't want to do anything
            assert self.__previous_req_handler is not self.req_handler
            assert bool(self.__previous_req_handler.response_queue)
            return

        response_id, response_cb, result, unpack_response, has_args = self.req_handler.response_queue.popleft()

        assert response_id == expect_response_id
        try:
            if has_args:
                if unpack_response and isinstance(result, tuple):
                    response_cb(*result)
                else:
                    response_cb(result)
            else:
                response_cb()

        except Exception as exc:
            ignore = isinstance(exc, RuntimeError) and str(exc).startswith('wrapped C/C++')
            if self._global_error_handler and not ignore:
                self._global_error_handler.on_response_cb_error(AsyncErrorInfo(exc, None, response_cb))


class AsyncRequestHandler(QObject):
    """
    The AsyncRequestHandler is in charge of calling the callable object with given arguments and kw arguments,
    and either emitting a signal to provide the return values of callable object to the response callback
    (if there was one defined) or handling any error via global_error_handler.
    """
    sig_respond_async = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.global_error_handler = None

        self.response_queue = deque()
        self.call_queue = deque()
        self.next_call_id = 0
        self.next_response_id = 0

    @pyqtSlot(int)
    def accept_request(self, expect_call_id: int):
        """
        Call the given callable_obj with given args and kw args. Send the return value back via sig_respond_async
        signal to response_cb, or call error_cb if error occurred in call to callable_obj.
        """
        call_id, callable_obj, args, kwargs, response_cb, unpack_response, error_cb = self.call_queue.popleft()
        assert expect_call_id == call_id

        try:
            result = callable_obj(*args, **kwargs)
            if response_cb:
                self.__send_response(response_cb, result, unpack_response=unpack_response)

        except Exception as exc:
            error_info = AsyncErrorInfo(exc, callable_obj, response_cb)
            if error_cb is None and self.global_error_handler:
                error_cb = self.global_error_handler.on_call_error

            if error_cb:
                # self.sig_respond_async.emit(error_cb, error_info)
                self.__send_response(error_cb, error_info)

    def __send_response(self, response_cb: Either[ResponseCB, AsyncRequestErrorCallable],
                        result: Any, unpack_response: bool = True):
        response_id = self.next_response_id
        self.next_response_id += 1
        import inspect
        has_args = bool(inspect.signature(response_cb).parameters)
        response_info = (response_id, response_cb, result, unpack_response, has_args)
        self.response_queue.append(response_info)
        self.sig_respond_async.emit(response_info[0])


class AsyncRequest:
    """
    This class supports asynchronously calling *any* callable in a different thread, and asynchronously
    receiving the return values in the current thread. It does this by using
    PyQt's queued signal/slot system.

    To use it, give the target thread to set_target_thread once, then call call() as many times as desired.
    It does not matter in which thread the callable or the response callback were defined, or if they are
    QObject or not (and hence if they are QObject, which thread they have been moved to is irrelevant). If
    the app event loop and target thread have been started, the callable will executed in that target thread,
    and its results will be given to the response callback (if one was specified) in the main thread.

    The above makes AsyncRequest very versatile: it allows the callable to be a lambda to access properties from the
    target thread, or a local function to package multiple data obtained from the target thread,
    and allows the response callback to be a local function to process the data received. Example:

        class Foo:
            @property
            def prop1(self):
                return 123

        class Baz:
            @property
            def prop2(self):
                return 'abc'

        foo = Foo()
        baz = Baz()

        def on_response(prop1, prop2):
            print('foo:', prop1, 'baz:', prop2)

        # get property values from two objects, and process them as separate parameters in response callback:
        AsyncRequest.call(lambda: (foo.prop1, baz.prop2), response_cb=on_response)

    Note: by default, errors in either the callable or the response callback are silently ignored. To
    log the error, call AsyncRequest.set_global_error_handler(SimpleAsyncErrorHandler()). For more advanced error
    handler, given set_global_error_handler() an object that implements IAsyncErrorHandler.
    """

    _requester = None  # singleton object to handle making requests for function calls

    @staticmethod
    def set_target_thread(backend_thread: QThread):
        """
        Set in which thread requests (made later via call()) will be executed (asynchronously). Until first
        call to this method, AsyncRequest is said to be unbound.
        Notes:
        - One call to this method is necessary and sufficient so that call() can be used.
        - If call this method again for different thread, will unbind from previous
        """
        if backend_thread is None:
            raise ValueError('backend_thread cannot be None')

        if AsyncRequest._requester is None:
            AsyncRequest._requester = AsyncRequester(backend_thread)
        else:
            AsyncRequest._requester.reset(backend_thread)

    @staticmethod
    def is_bound() -> bool:
        """Return true if AsyncRequest has been setup with a target thread, false otherwise"""
        return AsyncRequest._requester is not None

    @staticmethod
    def set_global_error_handler(handler: IAsyncErrorHandler = None):
        """
        Set or unset the error handler. It must have the two methods defined by IAsyncErrorHandler.
        """
        AsyncRequest._requester.set_global_error_handler(handler)

    @staticmethod
    def call(callable_obj: Callable, *args, response_cb: ResponseCB = None, unpack_response=True,
             error_cb: AsyncRequestErrorCallable = None, **kwargs):
        """
        Make an asynchronous call to the given callable, with given positional and named arguments, in the
        thread given earlier to set_target_thread(): ie, call callable_obj(*args) (or callable_obj(*args, **kwargs)
        if kwargs is not None) asynchronously in the target thread.

        If the response_cb is given, it will be called in the *current thread* with the data returned by the
        callable_obj. The default behavior is that response_cb(result) will be called if only one returned value,
        whereas response_cb(*result) will be called if callable_obj() returned a tuple. This allows
        for a more natural API of the callback. If error_cb is given, it will be called if callable_obj raised
        an exception. It will be called with one argument, an instance of AsyncErrorInfo object.

        Example:

            def backend_func():
                return (1, 'a', None)
            def on_response(num, letter, obj):
                print(num, letter, obj)
            def on_error(exc_info):
                show_message(exc_info.msg)
                log.error("Error in call to {}: {}", backend_func, exc_info.msg)
                log.error("    Traceback: {}", exc_info.traceback)
            AsyncRequest.call(backend_func, response_cb=on_response, error_cb=on_error)

        """
        if error_cb:
            assert len(inspect.signature(error_cb).parameters) == 1, "The error_cb must have exactly one parameter"

        if AsyncRequest._requester is None:
            raise RuntimeError("BUG: AsyncRequest.set_target_thread() not called yet")

        # AsyncRequest._requester.sig_request_async.emit(callable_obj, args, kwargs or {}, response_cb, error_cb)
        call_info = callable_obj, args, kwargs or {}, response_cb, unpack_response, error_cb
        AsyncRequest._requester.queue_request(call_info)


class SimpleAsyncErrorHandler(IAsyncErrorHandler):
    """
    Simple error handler that can be given to AsyncRequest.set_global_error_handler.
    """

    def __init__(self, stream=None):
        self._stream = stream

    @override(IAsyncErrorHandler)
    def on_call_error(self, exc_info: AsyncErrorInfo):
        log.error('Error in async request {}: {}', exc_info.call_obj, exc_info.exc)
        log.error(exc_info.traceback)
        if self._stream is not None:
            self._stream.write('Error in async request {}: {}'.format(exc_info.call_obj, exc_info.msg))
            self._stream.write(exc_info.traceback)

    @override(IAsyncErrorHandler)
    def on_response_cb_error(self, exc_info: AsyncErrorInfo):
        log.error('Error in async response {}: {}', exc_info.response_cb, exc_info.exc)
        log.error(exc_info.traceback)
        if self._stream is not None:
            self._stream.write('Error in async response {}: {}'.format(exc_info.response_cb, exc_info.msg))
            self._stream.write(exc_info.traceback)


class SyncRequest:
    """Replacement for AsyncRequest when mono-thread"""

    @staticmethod
    def set_target_thread(backend_thread: QThread):
        pass

    @staticmethod
    def is_bound() -> bool:
        return True

    @staticmethod
    def set_global_error_handler(handler: IAsyncErrorHandler = None):
        pass

    @staticmethod
    def call(callable_obj: Callable, *args, response_cb: ResponseCB = None,
             error_cb: IAsyncErrorHandler = None, **kwargs):
        if error_cb:
            assert len(inspect.signature(error_cb).parameters) == 1, "The error_cb must have exactly one parameter"

        try:
            result = callable_obj(*args, **kwargs)
            if response_cb:
                if isinstance(result, tuple):
                    response_cb(*result)
                else:
                    response_cb(result)
        except Exception as exc:
            if error_cb:
                error_cb(exc)
            else:
                log.error(exc)

# AsyncRequest = SyncRequest
