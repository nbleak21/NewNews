"""Placeholder test: proves the environment and package import work.

Delete this file once real tests exist.
"""
# HINT: one test file per module (test_config.py, test_select.py, ...).
# HINT: load saved feeds from tests/fixtures/; tests must never hit the network.

import commute_news


def test_package_imports() -> None:
    assert commute_news.__version__
