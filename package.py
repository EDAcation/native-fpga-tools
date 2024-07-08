#!/usr/bin/env python3

import os
import shutil
import subprocess
import glob
import re
import sys
import json
import datetime
import sys
import threading

import click

RELEASE_VER = datetime.datetime.now().strftime('%Y-%m-%d')
REPO = 'edacation/native-tools'
DOWNLOAD_BASE_URL = f'https://github.com/{REPO}/releases/download/{RELEASE_VER}'

CLEANUP_PATTERNS = [
    './*/python*/test',  # python unit tests
    './**/__pycache__',  # python caches

    # build workflow leftovers
    './.hash',

    # irrelevant build files
    './share/manifest.json',
    './share/man/',
    './environment*',
    './README'
]


def copy_tools(from_dir: str, to_dir: str) -> None:
    for tool_dir in os.listdir(from_dir):
        from_path = os.path.join(from_dir, tool_dir)
        if not os.path.isdir(from_path):
            continue

        to_path = os.path.join(to_dir, tool_dir)

        print(f'Copying tool: {from_path} => {to_path}')
        shutil.copytree(from_path, to_path)


def clean_tools(tools_dir: str) -> None:
    for tool_dir in os.listdir(tools_dir):
        tool_path = os.path.join(tools_dir, tool_dir)
        if not os.path.isdir(tool_path):
            continue

        # Write readable code challenge (IMPOSSIBLE)
        cleanup_paths = set(
            path for matches in
            (
                glob.glob(pattern, root_dir=tool_path, recursive=True)
                for pattern in CLEANUP_PATTERNS
            )
            for path in matches
        )
        
        for path in cleanup_paths:
            print(f'[{tool_dir}] Removing {path}')

            full_path = os.path.join(tool_path, path)
            try:
                if os.path.isfile(full_path):
                    os.remove(full_path)
                else:
                    shutil.rmtree(full_path)
            except FileNotFoundError:
                pass


def create_report(tools_dir: str) -> dict:
    sys.path += ['oss-cad-suite-build/']
    from src.base import buildCode, targets

    tools: list[dict] = []

    for tool_name in os.listdir(tools_dir):
        tool_path = os.path.join(tools_dir, tool_name)
        if not os.path.isdir(tool_path):
            continue

        try:
            full_hash = open(os.path.join(tool_path, '.hash')).read().strip()
        except FileNotFoundError:
            print(f'[!!!] Tool "{tool_name}" does not have a valid version! REMOVING!', file=sys.stderr)
            shutil.rmtree(tool_path)
            continue

        try:
            manifest = json.load(open(os.path.join(tool_path, 'share/manifest.json')))
            name = manifest["version"]["branding"]
            arch = manifest["version"]["arch"]
            tool = manifest["version"]["product"]

            if tool.endswith('-full'):
                tool = tool[:-len('-full')]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            print(f'[!!!] Tool "{tool_name}" does not have a valid manifest! REMOVING!', file=sys.stderr)
            shutil.rmtree(tool_path)
            continue

        tools.append({
            'friendly_name': name,
            'tool': tool,
            'arch': arch,
            'version': full_hash[:7],
            'download_url': DOWNLOAD_BASE_URL + f'/{tool_name}.tgz'
        })
    
    return {
        'version': RELEASE_VER,
        'tools': tools
    }


def package_tools(tools_dir: str) -> None:
    def _package_tool(tool_name):
        tool_path = os.path.join(tools_dir, tool_name)
        if not os.path.isdir(tool_path):
            return

        out_path = os.path.join(tools_dir, f'{tool_name}.tgz')

        print(f'[{tool_name}] Packing tgz...')
        subprocess.run(['tar', '-C', tools_dir, '-czf', out_path, tool_name], check=True)
        print(f'[{tool_name}] Deleting tool directory...')
        shutil.rmtree(tool_path)
        print(f'[{tool_name}] Finished packing')

    threads = [threading.Thread(target=_package_tool, args=[tool_name]) for tool_name in os.listdir(tools_dir)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

@click.command()
@click.option('--in-dir', help='Input tool directory', required=True)
@click.option('--out-dir', help='Output artifact directory', required=True)
@click.option('--report', help='Where to write the report file')
def package(in_dir: str, out_dir: str, report: str | None = None):
    if os.path.isdir(out_dir):
        print('Removing output directory')
        shutil.rmtree(out_dir)
    os.mkdir(out_dir)

    copy_tools(in_dir, out_dir)
    tools_report = create_report(out_dir)
    clean_tools(out_dir)
    package_tools(out_dir)

    if report:
        print(f'Writing report to {report}')
        with open(report, 'w+') as f:
            json.dump(tools_report, f, indent=2)


if __name__ == '__main__':
    package()
