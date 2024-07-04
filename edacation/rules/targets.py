"""
Contains custom OSS CAD Suite targets that should be built.

Targets called <toolname>-full are functionally equivalent to the existing <toolname> target,
but are built as a top_package. This means that it will contain the libraries necessary
to run it as a standalone tool.

This module gets called with cwd = <gitroot>/oss-cad-suite-build, so we can import from there.
"""

from src.base import Target

##### Yosys #####

# We override Yosys here because we do not want to bundle xdot / graphviz.
# The builder will be looking for a `yosys.sh` script in the `edacation/scripts/`
# directory, so to fix this it is symlinked to the 'default' yosys.sh file.
# Note that the symlink is only resolvable when `edacation/` is copied into the builder directory.

Target(
	name = 'yosys',
	sources = ['yosys'],
	dependencies = ['abc'],
)

Target(
    name='yosys-full',
    branding='Yosys (EDAcation)',
    top_package=True,
    readme='README.md',
	dependencies=[
        'yosys',
    ],
    resources = [
        'system-resources'
    ]
)
