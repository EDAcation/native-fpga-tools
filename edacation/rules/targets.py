"""
Contains custom OSS CAD Suite targets that should be built.

Targets called <toolname>-full are functionally equivalent to the existing <toolname> target,
but are built as a top_package. This means that it will contain the libraries necessary
to run it as a standalone tool.

This module gets called with cwd = <gitroot>/oss-cad-suite-build, so we can import from there.
"""

from src.base import Target

Target(
    name='yosys-full',
    branding='Yosys (EDAcation)',
    top_package=True,
    readme='README.md',
	dependencies=[
        'yosys',
    ],
    resources = [
        'system-resources-min'
    ]
)
