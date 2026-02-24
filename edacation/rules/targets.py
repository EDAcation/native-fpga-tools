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

Target(
    name = 'yosys',
    sources = ['yosys'],
    dependencies = ['abc'],
)

Target(
    name='yosys-full',
    branding='Yosys',
    top_package=True,
    readme='README.md',
    dependencies=[
        'yosys',
        'ghdl',
        'ghdl-yosys-plugin'
    ],
    resources = [
        'system-resources-min'
    ]
)

# FIXME: override ghdl to skip building for darwin-x64, whose source is currently missing in the upstream repository.
Target(
	name = 'ghdl-yosys-plugin',
	sources = [ 'ghdl-yosys-plugin' ],
	dependencies = [ 'ghdl', 'yosys' ],
	arch = [ 'linux-x64', 'darwin-arm64' ],
)

Target(
	name = 'ghdl',
	sources = [ 'ghdl' ],
	arch = [ 'linux-x64', 'darwin-arm64' ],
)

#### Nextpnr-generic ####

Target(
    name = 'nextpnr-generic',
    sources = [ 'nextpnr' ],
    dependencies = [ 'python3', 'nextpnr-bba', 'python3-native' ],
    resources = [ 'python3' ],
)

Target(
    name='nextpnr-generic-full',
    branding='Nextpnr (Generic)',
    top_package=True,
    readme='README.md',
    dependencies=[
        'nextpnr-generic',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### Nextpnr-ice40 ####

Target(
    name = 'nextpnr-ice40',
    sources = [ 'nextpnr' ],
    dependencies = [ 'python3', 'nextpnr-bba', 'icestorm-bba', 'python3-native' ],
    resources = [ 'python3' ],
    package = 'ice40',
)

Target(
    name='nextpnr-ice40-full',
    branding='Nextpnr (iCE40)',
    top_package=True,
    readme='README.md',
    dependencies=[
        'nextpnr-ice40',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### Nextpnr-ecp5 ####

Target(
    name = 'nextpnr-ecp5',
    sources = [ 'nextpnr' ],
    dependencies = [ 'python3', 'nextpnr-bba', 'prjtrellis-bba', 'python3-native' ],
    resources = [ 'python3' ],
    package = 'ecp5',
)

Target(
    name='nextpnr-ecp5-full',
    branding='Nextpnr (ECP5)',
    top_package=True,
    readme='README.md',
    dependencies=[
        'nextpnr-ecp5',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### iverilog ####

Target(
	name = 'iverilog-full',
    branding='ICARUS Verilog',
    top_package=True,
    readme='README.md',
	dependencies=[
        'iverilog',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### openFPGALoader ####

Target(
	name = 'openfpgaloader-full',
    branding='openFPGALoader',
    top_package=True,
    readme='README.md',
	dependencies=[
        'openfpgaloader',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### prjtrellis ####

Target(
    name = 'prjtrellis-full',
    branding='Project Trellis',
    top_package=True,
    readme='README.md',
    dependencies=[
        'prjtrellis',
    ],
    resources = [
        'system-resources-min'
    ]
)

#### icestorm ####

Target(
    name = 'icestorm-full',
    branding='Project IceStorm',
    top_package=True,
    readme='README.md',
    dependencies=[
        'icestorm',
    ],
    resources = [
        'system-resources-min'
    ]
)
