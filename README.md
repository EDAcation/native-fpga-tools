# Native FPGA Tools

Native tool bundles for synthesis & PnR.
These bundles are used in [EDAcation](https://github.com/edacation/vscode-edacation) to provide native Yosys & Nextpnr tools
without having to download the entire [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) tarball.

## Goals

This project has the following main goals:
- **Universal**: The selected tools should be available for the widest possible range of platforms;
- **Usable**: Every tool should come with all the necessary dependencies such that no additional setup is required;
- **Minimal**: Only the bare minimum should be contained in every tarball for the tool to run, nothing more.

## Supported Tools & Platforms

The following tools are supported:
- `nextpnr-ecp5`
- `nextpnr-generic`
- `nextpnr-ice40`
- `nextpnr-nexus`
- `yosys`

The following platforms are supported:
- `darwin-arm64`
- `darwin-x64`
- `linux-arm64`
- `linux-x64`
- `windows-x64`

# How To Use

To get an index of the currently supported tools, issue a GET request to the following URL:

`https://github.com/EDAcation/native-fpga-tools/releases/latest/download/tools.json`

The response is a JSON document that looks as follows:
```json
{
  "version": "2024-07-09",
  "tools": [
    {
      "friendly_name": "Nextpnr (Generic)",
      "tool": "nextpnr-generic",
      "arch": "darwin-arm64",
      "version": "5cecaba",
      "download_url": "https://github.com/edacation/native-fpga-tools/releases/download/2024-07-09/darwin-arm64-nextpnr-generic.tgz"
    },
    ...
  ]
}
```

Downloading the tool will result in a gzipped tarball (`.tgz`, `.tar.gz`) with the following directory structure:
```
<platform>-<tool-name>/
  bin/
    <tool-name>
    <other-executables>
  lib/
  license/
  share/
```

**Only** the `<platform>-<tool-name>/bin/<tool-name>` file is guaranteed to exist.

# Thanks

Many thanks to [yosysHQ](https://github.com/yosysHQ/) for Yosys, Nextpnr, oss-cad-suite-build and many other tools and repositories that we heavily rely on.
