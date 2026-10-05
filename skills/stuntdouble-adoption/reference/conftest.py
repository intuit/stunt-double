"""Root conftest.

Its presence makes pytest put this directory on ``sys.path`` so the tests can
import ``agent``, ``tools`` and ``mocking`` the same way the application does.
In a real project the package is installed and this file is unnecessary.
"""
