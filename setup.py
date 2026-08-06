#!/usr/bin/env python3
from setuptools import setup

setup(
    name="liquid-devil-rgb",
    version="1.0.0",
    description="Linux I2C RGB Lighting Control for PowerColor Radeon RX 7900 XTX Liquid Devil",
    py_modules=["liquid_devil_rgb"],
    entry_points={
        "console_scripts": [
            "liquid-devil-rgb = liquid_devil_rgb:main",
        ],
    },
)
