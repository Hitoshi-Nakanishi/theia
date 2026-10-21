import posixpath
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Union
from xml.etree import ElementTree as ET

from openpyxl.styles.numbers import BUILTIN_FORMATS
from openpyxl.utils.cell import coordinate_to_tuple
from python_calamine import CalamineWorkbook

# A workbook source is either a real file path, or an entry inside a zip
# expressed as (zip_path, inner_name).
Source = Union[Path, tuple[Path, str]]


@dataclass
class Sheet:
    name: str
    rows: list[list] = field(default_factory=list)
    loaded: bool = False
    merged_cells: list = field(default_factory=list)
    cell_formats: dict[tuple[int, int], str] | None = None


class Workbook:
    """Lazy Excel workbook. Sheet names are read up front; data is parsed
    only when a sheet is first requested, then cached in memory.

    The source can be either a path on disk or a tuple (zip_path, inner_name)
    pointing at an .xlsx entry inside a .zip archive.
    """

    def __init__(self, source: Source):
        self._xlsx = None
        self._xlsx_source = None
        self._number_formats = None
        self._sheet_paths = {}
        if isinstance(source, tuple):
            zip_path, inner = source
            self._zip_path = Path(zip_path)
            self._inner = inner
            self.path = self._zip_path / inner  # display-only synthetic path
            with zipfile.ZipFile(self._zip_path) as z:
                data = z.read(inner)
            self._cal = CalamineWorkbook.from_filelike(BytesIO(data))
            if Path(inner).suffix.lower() in {".xlsx", ".xlsm"}:
                self._xlsx_source = BytesIO(data)
        else:
            self.path = Path(source)
            self._zip_path = None
            self._inner = None
            self._cal = CalamineWorkbook.from_path(str(self.path))
            if self.path.suffix.lower() in {".xlsx", ".xlsm"}:
                self._xlsx_source = self.path

        self.sheets: dict[str, Sheet] = {name: Sheet(name=name) for name in self._cal.sheet_names}
        self._loaded: OrderedDict[str, None] = OrderedDict()

    @property
    def sheet_names(self) -> list[str]:
        return list(self.sheets.keys())

    def load_sheet(self, name: str, cached_rows: list | None = None) -> Sheet:
        sheet = self.sheets[name]
        if not sheet.loaded:
            source_sheet = self._cal.get_sheet_by_name(name)
            sheet.rows = source_sheet.to_python(skip_empty_area=False) if cached_rows is None else cached_rows
            sheet.merged_cells = source_sheet.merged_cell_ranges or []
            sheet.loaded = True
        self._loaded[name] = None
        self._loaded.move_to_end(name)
        while len(self._loaded) > 1:
            old, _ = self._loaded.popitem(last=False)
            self.sheets[old].rows = []
            self.sheets[old].loaded = False
            self.sheets[old].cell_formats = None
        return sheet

    def cell_formats(self, name: str) -> dict[tuple[int, int], str]:
        """Stream number formats for the active OOXML sheet without decoding values again."""
        if self.sheets[name].cell_formats is not None:
            return self.sheets[name].cell_formats
        if self._xlsx_source is None:
            return {}
        if self._xlsx is None:
            self._xlsx = zipfile.ZipFile(self._xlsx_source)
        if self._number_formats is None:
            formats = dict(BUILTIN_FORMATS)
            if "xl/styles.xml" in self._xlsx.namelist():
                styles = ET.fromstring(self._xlsx.read("xl/styles.xml"))
                for fmt in styles.findall("{*}numFmts/{*}numFmt"):
                    formats[int(fmt.attrib["numFmtId"])] = fmt.attrib["formatCode"]
                self._number_formats = [
                    formats.get(int(xf.get("numFmtId", "0")), "General") for xf in styles.findall("{*}cellXfs/{*}xf")
                ]
            else:
                self._number_formats = []
            relationships = ET.fromstring(self._xlsx.read("xl/_rels/workbook.xml.rels"))
            targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships if rel.get("TargetMode") != "External"}
            workbook = ET.fromstring(self._xlsx.read("xl/workbook.xml"))
            for sheet in workbook.findall("{*}sheets/{*}sheet"):
                relation = next(value for key, value in sheet.attrib.items() if key.endswith("}id"))
                target = targets[relation]
                self._sheet_paths[sheet.attrib["name"]] = (
                    target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
                )
        result = {}
        with self._xlsx.open(self._sheet_paths[name]) as stream:
            for _, element in ET.iterparse(stream, events=("end",)):
                if element.tag.rsplit("}", 1)[-1] == "c":
                    style = int(element.get("s", "0"))
                    if style < len(self._number_formats):
                        fmt = self._number_formats[style]
                        if fmt != "General":
                            result[coordinate_to_tuple(element.attrib["r"])] = fmt
                element.clear()
        self.sheets[name].cell_formats = result
        return result

    def close(self):
        self._cal.close()
        if self._xlsx is not None:
            self._xlsx.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def list_zip_xlsx(zip_path: Path) -> list[str]:
    """Return inner names of Excel files in the zip, sorted by basename."""
    suffixes = {".xlsx", ".xls", ".xlsm", ".xlsb"}
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/") and Path(n).suffix.lower() in suffixes]
    names.sort(key=lambda n: Path(n).stem.lower())
    return names
