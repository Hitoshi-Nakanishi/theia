"""Repeatable native-viewer timing and resident-memory check using fictional data."""

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time


def resident_mib():
    if sys.platform == "win32" and os.environ.get("WINDIR"):
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "pool_peak", "pool", "nonpaged_peak", "nonpaged", "pagefile", "pagefile_peak")
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.working / 1024**2
    import subprocess
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())])) / 1024


def prepare(folder):
    from openpyxl import Workbook

    folder.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    for name in ("Summary", "Forecast", "Valuation"):
        sheet = workbook.create_sheet(name)
        sheet.append(["Metric", *[f"FY{2020 + c}" for c in range(1, 16)]])
        for row in range(1, 1501):
            sheet.append([f"Metric {row}", *[round(row * col / 11, 2) for col in range(1, 16)]])
    reference = folder / "Company_00.xlsx"
    workbook.save(reference)
    payload = reference.read_bytes()
    for index in range(1, 24):
        (folder / f"Company_{index:02}.xlsx").write_bytes(payload)


def run(args):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    started = time.perf_counter()
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase
    from theia.app import MainWindow

    app = QApplication([])
    if sys.platform == "win32" and os.environ.get("WINDIR"):
        for font in ("arial.ttf", "segoeui.ttf", "meiryo.ttc"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / font))
    app.setFont(QFont("Arial", 10))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(args.fixture / ".settings"))
    settings = QSettings("Theia", "Theia")
    settings.clear()
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    result = {"startup_ms": (time.perf_counter() - started) * 1000, "idle_mib": resident_mib()}
    started = time.perf_counter()
    window.open_folder(args.fixture)
    app.processEvents()
    result["folder_ms"] = (time.perf_counter() - started) * 1000
    timings = []
    companies = [item for item in window._companies_model.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive)
                 if item.data(Qt.UserRole) is not None]
    for item in companies:
        started = time.perf_counter()
        window.company_tree.setCurrentIndex(window._companies_proxy.mapFromSource(item.index()))
        for row in range(window._sheets_proxy.rowCount()):
            window.sheet_list.setCurrentIndex(window._sheets_proxy.index(row, 0))
            app.processEvents()
        timings.append((time.perf_counter() - started) * 1000)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    result.update(companies=len(companies), sheets_per_company=3, rows_per_sheet=1501, columns=16,
                  company_median_ms=statistics.median(timings), company_p95_ms=sorted(timings)[int(len(timings)*.95)],
                  visited_mib=resident_mib(), workbook_cache=len(window._workbooks), model_cache=len(window._sheet_model_cache))
    window.open_path(Path(__file__).resolve().parents[1] / "examples/demo_models/0000.T_Demo_Model.xlsx")
    app.processEvents()
    if args.screenshot:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.screenshot))
    window.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.fixture)
    else:
        run(args)
