#!/usr/bin/env python3
from setuptools import find_packages, setup

setup(
    name="liquid-devil-rgb",
    version="1.0.0",
    description="Linux I2C RGB Lighting Control for PowerColor Radeon RX 7900 XTX Liquid Devil",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        "console_scripts": [
            "liquid-devil-rgb = liquid_devil_rgb.cli:main",
        ],
    },
)
