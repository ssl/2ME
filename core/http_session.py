"""
HTTP access for 2ME Domain Checker Framework
Reuses connections, so repeated lookups at the same server skip the TLS handshake.
"""

import threading

import requests

_local = threading.local()


def session():
    """
    The requests session of the current thread.

    A session is not safe to share between threads, so each thread gets
    its own; it keeps the connections to the servers that thread talks to.
    """
    current = getattr(_local, 'session', None)
    if current is None:
        current = _local.session = requests.Session()
    return current


def get(url, **kwargs):
    """Like requests.get, over the current thread's kept-alive connections."""
    return session().get(url, **kwargs)


def post(url, **kwargs):
    """Like requests.post, over the current thread's kept-alive connections."""
    return session().post(url, **kwargs)
