#!/usr/bin/env python3

import os

import click

@click.command()
@click.option('--in-dir', help='Input tool directory', required=True)
@click.option('--out-dir', help='Output artifact directory', required=True)
@click.option('--report', help='Where to write the report file')
def package(in_dir: str, out_dir: str, report: str | None = None):
    # TODO: actually package!
    os.mkdir(out_dir)
    if report:
        with open(report, 'w+') as f:
            f.write('{}')


if __name__ == '__main__':
    package()
