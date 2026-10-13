"""Pywinpty 3 requires its native console host executables as well as DLLs."""

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("winpty", includes=["*.exe"])
