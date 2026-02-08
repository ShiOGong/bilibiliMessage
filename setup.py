from setuptools import setup
import os

APP = ["menubar.py"]
DATA_FILES = ["main.py", "config.example.json", "config.app.example.json"]

iconfile = None
if os.path.exists("BiliNotify.icns"):
    iconfile = "BiliNotify.icns"

OPTIONS = {
    "argv_emulation": False,
    "packages": ["requests", "rumps", "qrcode", "PIL"],
    "excludes": [
        "wheel",
        "setuptools._vendor",
        "setuptools._vendor.packaging",
        "setuptools._vendor.jaraco",
        "setuptools._vendor.autocommand",
        "setuptools._vendor.backports",
        "setuptools._vendor.importlib_metadata",
        "setuptools._vendor.zipp",
        "setuptools._vendor.more_itertools",
    ],
    "plist": {
        "CFBundleName": "B站关注通知",
        "CFBundleDisplayName": "B站关注通知",
        "LSUIElement": True,
    },
}
if iconfile:
    OPTIONS["iconfile"] = iconfile

setup(
    app=APP,
    name="B站关注通知",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
