"""Python *site customisation* module.

This project opts out of PyTest's automatic third-party plugin loading because
some globally installed plugins (e.g. *langsmith*) pull in heavy dependencies
that conflict with our own requirements.  Setting the environment variable
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` *before* PyTest starts prevents those
plugins from being imported and keeps the test environment hermetic.

Python automatically imports *sitecustomize* at interpreter start-up (if it
exists on the PYTHONPATH), so this file is the earliest reliable place to set
that variable for all developer and CI workflows.
"""

import os

# Disable auto-loading of entry-point plugins to keep the environment hermetic.
# Doing this unconditionally is safe and avoids obscure dependency clashes.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

# Explicitly block the problematic *langsmith* plugin in case autoload remains
# enabled in certain environments.  We inject it via PYTEST_ADDOPTS so the
# option is visible before pytest parses its command-line arguments.
_existing_addopts = os.environ.get("PYTEST_ADDOPTS", "")
for name in ("langsmith", "langsmith_plugin"):
    if f"-p no:{name}" not in _existing_addopts:
        _existing_addopts = (f"-p no:{name} " + _existing_addopts).strip()
os.environ["PYTEST_ADDOPTS"] = _existing_addopts 