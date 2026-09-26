"""Records which interpreter actually ran the test suite.

The test always passes if it can import its dependencies, as a real suite
would. The experiment compares probe.json with the interpreter the job
asked for.
"""
import json
import os
import sys

import yaml


def test_probe():
    probe = {
        "version": "%d.%d.%d" % sys.version_info[:3],
        "executable": sys.executable,
        "real_executable": os.path.realpath(sys.executable),
        "yaml_file": yaml.__file__,
        "yaml_cext": bool(getattr(yaml, "__with_libyaml__", False)),
    }
    with open(os.environ.get("PROBE_OUT", "probe.json"), "w") as f:
        json.dump(probe, f)
