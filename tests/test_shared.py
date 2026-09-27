import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from analyze_sample import shares_across_python  # noqa: E402

WF = """
jobs:
  t:
    strategy:
      matrix:
{matrix}
    steps: []
"""


def test_one_key_for_several_pythons_is_shared():
    m = '        python-version: ["3.10", "3.11", "3.12"]'
    assert shares_across_python(WF.format(matrix=m), "t", "venv-${{ runner.os }}-${{ hashFiles('x') }}")


def test_matrix_variable_tied_to_python_separates_them():
    m = """        include:
          - {env_name: py_pinned, python-version: "3.11"}
          - {env_name: py_latest, python-version: "3.13"}"""
    assert not shares_across_python(WF.format(matrix=m), "t", "venv-${{ matrix.env_name }}")


def test_single_python_is_not_shared():
    m = '        python-version: ["3.12"]'
    assert not shares_across_python(WF.format(matrix=m), "t", "venv-${{ hashFiles('x') }}")


def test_os_in_key_does_not_separate_python():
    m = '        os: [ubuntu-latest, macos-latest]\n        python-version: ["3.11", "3.12"]'
    assert shares_across_python(WF.format(matrix=m), "t", "venv-${{ matrix.os }}")
