#!/usr/bin/env python3

import sys
import setuptools

import miss_hit.version

with open("README.md", "r") as fd:
    long_description = fd.read()

setuptools.setup(
    name="miss_hit",
    version=miss_hit.version.VERSION,
    author="Florian Schanda",
    author_email="florian@schanda.org.uk",
    description="Code formatting and code metrics for programs written in the MATLAB/Simulink and Octave languages.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/florianschanda/miss_hit",
    project_urls={
        "Bug Tracker"   : "https://github.com/florianschanda/miss_hit/issues",
        "Documentation" : "https://florianschanda.github.io/miss_hit/",
        "Source Code"   : "https://github.com/florianschanda/miss_hit",
    },
    license="GNU General Public License v3",
    packages=["miss_hit"],
    python_requires=">=3.6, <4",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Compilers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Utilities"
    ],
    entry_points={
        "console_scripts": [
            "mh_style = miss_hit.mh_style:main",
            "mh_metric = miss_hit.mh_metric:main",
        ],
    },
)
