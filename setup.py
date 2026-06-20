"""Build Cython extension for ArrowSheetModel hot path.

Run:  python setup.py build_ext --inplace
      (or:  task build-cython)

Requires Cython and a C compiler (MSVC on Windows, gcc/clang on macOS/Linux).
The extension is optional — arrow_model.py falls back to pure Python when the
compiled .pyd/.so is not found.
"""

from setuptools import setup

try:
    from Cython.Build import cythonize
    ext_modules = cythonize("theia/_arrow_fast.pyx", language_level=3)
except ImportError:
    ext_modules = []

setup(ext_modules=ext_modules)
