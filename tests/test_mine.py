import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mine_key_fixes import classify_change, key_pairs  # noqa: E402

PATCH = """@@ -10,7 +10,7 @@ jobs:
       - uses: actions/cache@v4
         with:
           path: .venv
-          key: venv-${{ hashFiles('poetry.lock') }}
+          key: venv-${{ steps.py.outputs.python-version }}-${{ hashFiles('poetry.lock') }}
@@ -30,3 +30,3 @@
-          key: v1-${{ runner.os }}-venv
+          key: v2-${{ runner.os }}-venv
"""


def test_pairs_and_kinds():
    pairs = key_pairs(PATCH)
    assert len(pairs) == 2
    assert classify_change(*pairs[0]) == "adds_interpreter"
    assert classify_change(*pairs[1]) == "manual_bust"


def test_other():
    assert classify_change("a-${{ hashFiles('x') }}", "b-${{ hashFiles('y') }}") == "other"


def test_version_literal_is_not_a_bust():
    assert classify_change("poetry-3.8-${{ hashFiles('a') }}", "poetry-3.9-${{ hashFiles('a') }}") == "version_literal"
    assert classify_change("yarn-12.x-k", "yarn-16.x-k") == "version_literal"
    assert classify_change("poetry-ubuntu-0  # increment to reset cache",
                           "poetry-ubuntu-1  # increment to reset cache") == "manual_bust"
    assert classify_change("v3-tests-${{ hashFiles('setup.py') }}", "v4-tests-${{ hashFiles('setup.py') }}") == "manual_bust"
