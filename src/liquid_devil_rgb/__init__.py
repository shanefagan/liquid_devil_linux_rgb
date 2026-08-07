"""PowerColor Radeon RX 7900 XTX Liquid Devil RGB Controller."""

from importlib.metadata import PackageNotFoundError, version

from liquid_devil_rgb.cli import LiquidDevilRGB, find_oem_i2c_bus, main

try:
    __version__ = version("liquid-devil-rgb")
except PackageNotFoundError:
    __version__ = "1.0.0"

__all__ = ["LiquidDevilRGB", "__version__", "find_oem_i2c_bus", "main"]
