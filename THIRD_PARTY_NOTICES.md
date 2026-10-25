# Third-party software

Theia's original source is under the [MIT License](LICENSE). That license does not replace the licenses of its dependencies.
The source distribution and application wheel do not contain Qt, Arrow or other dependency binaries; pip installs them as
separate packages with their upstream license files.

| Package | Upstream license |
| --- | --- |
| [PySide6-Essentials](https://pypi.org/project/PySide6-Essentials/) and [shiboken6](https://pypi.org/project/shiboken6/) | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| [python-calamine](https://pypi.org/project/python-calamine/) | MIT |
| [openpyxl](https://pypi.org/project/openpyxl/) and [et-xmlfile](https://pypi.org/project/et-xmlfile/) | MIT |
| [pyarrow](https://pypi.org/project/pyarrow/) (optional) | Apache-2.0 |

The table reflects the metadata of the dependencies checked for this source release. Their binary packages can contain
additional components and notices; preserve those upstream files when redistributing them.

## Qt distribution

The application imports Qt Core, Gui and Widgets from PySide6-Essentials. It does not require PySide6-Addons. The application
uses the separately installed shared libraries; users can replace the installation. Qt remains under its own license terms,
including notices and corresponding-source obligations when redistributing Qt binaries under LGPL. An MIT license on Theia
does not waive them. See [Qt's LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations) and the
[Qt for Python license inventory](https://doc.qt.io/qtforpython-6/licenses.html).

This project supplies Python source and a wheel, not a frozen executable bundling Qt. A distributor preparing such an
executable must review its actual bundled modules, retain their notices and license texts, provide the required source or
source offer, and preserve the user's ability to replace the libraries. The optional Cython accelerator builds only Theia
code; it does not statically link Qt.
