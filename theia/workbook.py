import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Union

from python_calamine import CalamineWorkbook

# A workbook source is either a real file path, or an entry inside a zip
# expressed as (zip_path, inner_name).
Source = Union[Path, tuple[Path, str]]


@dataclass
class Sheet:
    name: str
    rows: list[list] = field(default_factory=list)
    loaded: bool = False


class Workbook:
    """Lazy Excel workbook. Sheet names are read up front; data is parsed
    only when a sheet is first requested, then cached in memory.

    The source can be either a path on disk or a tuple (zip_path, inner_name)
    pointing at an .xlsx entry inside a .zip archive.
    """

    def __init__(self, source: Source):
        if isinstance(source, tuple):
            zip_path, inner = source
            self._zip_path = Path(zip_path)
            self._inner = inner
            self.path = self._zip_path / inner  # display-only synthetic path
            with zipfile.ZipFile(self._zip_path) as z:
                data = z.read(inner)
            self._cal = CalamineWorkbook.from_filelike(BytesIO(data))
        else:
            self.path = Path(source)
            self._zip_path = None
            self._inner = None
            self._cal = CalamineWorkbook.from_path(str(self.path))

        self.sheets: dict[str, Sheet] = {
            name: Sheet(name=name) for name in self._cal.sheet_names
        }
        self._loaded: OrderedDict[str, None] = OrderedDict()

    @property
    def sheet_names(self) -> list[str]:
        return list(self.sheets.keys())

    def load_sheet(self, name: str) -> Sheet:
        sheet = self.sheets[name]
        if not sheet.loaded:
            sheet.rows = self._cal.get_sheet_by_name(name).to_python(skip_empty_area=False)
            sheet.loaded = True
        self._loaded[name] = None
        self._loaded.move_to_end(name)
        while len(self._loaded) > 3:
            old, _ = self._loaded.popitem(last=False)
            self.sheets[old].rows = []
            self.sheets[old].loaded = False
        return sheet

    def close(self):
        self._cal.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def list_zip_xlsx(zip_path: Path) -> list[str]:
    """Return inner names of Excel files in the zip, sorted by basename."""
    suffixes = {".xlsx", ".xls", ".xlsm", ".xlsb"}
    with zipfile.ZipFile(zip_path) as z:
        names = [
            n for n in z.namelist()
            if not n.endswith("/") and Path(n).suffix.lower() in suffixes
        ]
    names.sort(key=lambda n: Path(n).stem.lower())
    return names
