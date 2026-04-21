#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import subprocess
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml

DEFAULT_ARCHES = [
    "linux-x64",
    "linux-arm64",
    "windows-x64",
    "darwin-x64",
    "darwin-arm64",
]

DEFAULT_TARGETS = [
    "yosys",
    "nextpnr-generic",
    "nextpnr-ice40",
    "nextpnr-ecp5",
    "iverilog",
    "openfpgaloader",
    "prjtrellis",
    "icestorm",
]


@dataclass
class Job:
    name: str
    arch: str
    target: str
    is_top_package: bool
    needs: set[str] = field(default_factory=set)
    download_deps: set[str] = field(default_factory=set)


class Args(argparse.Namespace):
    repo_root: str = "."
    output: str = ".github/workflows/build.yml"
    rules: str = "default,edacation"
    arches: str = ",".join(DEFAULT_ARCHES)
    targets: str = ",".join(DEFAULT_TARGETS)
    cron: str = "0 1 * * *"


def _extract_yaml_document(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("name:"):
            return "\n".join(lines[i:])
    raise ValueError("No YAML document found in builder output")


def _yaml_safe_load(text: str) -> object:
    return cast(object, yaml.safe_load(text))


def _parse_job_name(name: str, arches: Iterable[str]) -> tuple[str, str]:
    for arch in arches:
        prefix = f"{arch}-"
        if name.startswith(prefix):
            return arch, name[len(prefix) :]
    raise ValueError(f"Cannot infer architecture from job name: {name}")


def parse_generated_ci(yaml_text: str, arches: list[str]) -> dict[str, Job]:
    loaded_obj = _yaml_safe_load(_extract_yaml_document(yaml_text))
    if not isinstance(loaded_obj, dict):
        raise ValueError("Generated YAML does not contain a jobs section")

    loaded_dict = cast(dict[object, object], loaded_obj)
    jobs_raw_obj = loaded_dict.get("jobs")
    if jobs_raw_obj is None:
        raise ValueError("Generated YAML does not contain a jobs section")

    if not isinstance(jobs_raw_obj, dict):
        raise ValueError("Generated YAML jobs section is malformed")
    jobs_raw_dict = cast(dict[object, object], jobs_raw_obj)

    job_line_re = re.compile(
        r"./builder.py build --arch=([^ ]+) --target=([^ ]+) --single( --tar)?"
    )
    jobs: dict[str, Job] = {}

    for name_obj, job_obj in jobs_raw_dict.items():
        if not isinstance(name_obj, str):
            continue
        if not isinstance(job_obj, dict):
            continue
        name = name_obj
        job_raw = cast(dict[object, object], job_obj)

        arch, target = _parse_job_name(name, arches)

        needs: set[str] = set()
        download_deps: set[str] = set()
        run_arch: str | None = None
        run_target: str | None = None
        is_top_package: bool | None = None

        raw_needs = job_raw.get("needs")
        if isinstance(raw_needs, str):
            needs.add(raw_needs)
        elif isinstance(raw_needs, list):
            for need in cast(list[object], raw_needs):
                needs.add(str(need))

        steps_obj = job_raw.get("steps", [])
        if isinstance(steps_obj, list):
            for step_obj in cast(list[object], steps_obj):
                if not isinstance(step_obj, dict):
                    continue
                step = cast(dict[object, object], step_obj)

                step_name = step.get("name")
                if isinstance(step_name, str) and step_name.startswith("Download "):
                    download_deps.add(step_name[len("Download ") :].strip())

                run_cmd = step.get("run")
                if isinstance(run_cmd, str) and "./builder.py build" in run_cmd:
                    m = job_line_re.search(run_cmd)
                    if m:
                        run_arch = m.group(1)
                        run_target = m.group(2)
                        is_top_package = m.group(3) is None

        if run_arch is None or run_target is None or is_top_package is None:
            raise ValueError(f"Failed to parse build command from job '{name}'")

        if run_arch != arch or run_target != target:
            raise ValueError(
                f"Parsed command does not match job name for '{name}': arch={run_arch}, target={run_target}"
            )

        jobs[name] = Job(
            name=name,
            arch=arch,
            target=target,
            is_top_package=is_top_package,
            needs=needs,
            download_deps=download_deps,
        )

    return jobs


def run_ci_generation(
    builder_dir: Path, arch: str, full_target: str, rules: str
) -> str:
    cmd = [
        "./builder.py",
        "ci",
        f"--rules={rules}",
        f"--arch={arch}",
        f"--target={full_target}",
    ]
    completed = subprocess.run(
        cmd,
        cwd=builder_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def merge_jobs(job_sets: Iterable[dict[str, Job]]) -> dict[str, Job]:
    merged: dict[str, Job] = {}

    for jobs in job_sets:
        for name, job in jobs.items():
            if name not in merged:
                merged[name] = Job(
                    name=job.name,
                    arch=job.arch,
                    target=job.target,
                    is_top_package=job.is_top_package,
                    needs=set(job.needs),
                    download_deps=set(job.download_deps),
                )
                continue

            current = merged[name]
            if (
                current.arch != job.arch
                or current.target != job.target
                or current.is_top_package != job.is_top_package
            ):
                raise ValueError(f"Conflicting definitions for job '{name}'")

            current.needs.update(job.needs)
            current.download_deps.update(job.download_deps)

    return merged


def compute_required_jobs(all_jobs: dict[str, Job], roots: list[str]) -> set[str]:
    required: set[str] = set()
    stack = list(roots)

    while stack:
        name = stack.pop()
        if name in required:
            continue
        if name not in all_jobs:
            raise ValueError(f"Required job '{name}' is missing from merged CI graph")

        required.add(name)
        job = all_jobs[name]

        for dep in sorted(job.needs | job.download_deps):
            if dep in all_jobs and dep not in required:
                stack.append(dep)

    return required


def topological_order(jobs: dict[str, Job], required: set[str]) -> list[str]:
    indegree: dict[str, int] = {name: 0 for name in required}
    graph: dict[str, set[str]] = defaultdict(set)

    for name in required:
        deps = (jobs[name].needs | jobs[name].download_deps) & required
        indegree[name] = len(deps)
        for dep in deps:
            graph[dep].add(name)

    queue = deque(sorted([name for name, deg in indegree.items() if deg == 0]))
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for nxt in sorted(graph[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(ordered) != len(required):
        missing = sorted(required - set(ordered))
        raise ValueError(f"Dependency cycle detected across jobs: {missing}")

    return ordered


def _append_download_and_extract_steps(
    steps: list[dict[str, object]], job: Job, available: set[str]
) -> None:
    for dep in sorted(job.download_deps):
        if dep not in available:
            continue

        steps.extend(
            [
                {
                    "name": f"Download {dep}",
                    "uses": "actions/download-artifact@v4",
                    "with": {"name": dep, "path": f"_deps/{dep}"},
                },
                {
                    "name": f"Extract {dep}",
                    "run": f"tar -xzf _deps/{dep}/*.tgz -C oss-cad-suite-build",
                },
            ]
        )


def render_workflow(
    jobs: dict[str, Job],
    ordered_jobs: list[str],
    full_roots: list[str],
    cron: str,
) -> str:
    workflow: dict[str, object] = {
        "name": "Build",
        "on": {
            "workflow_dispatch": {},
            "schedule": [{"cron": cron}],
        },
        "permissions": {
            "contents": "write",
            "actions": "write",
        },
        "jobs": {},
    }

    jobs_section = workflow["jobs"]
    if not isinstance(jobs_section, dict):
        raise ValueError("Internal error while constructing workflow jobs")

    available = set(ordered_jobs)

    for job_name in ordered_jobs:
        job = jobs[job_name]
        deps = sorted((job.needs | job.download_deps) & available)

        steps: list[dict[str, object]] = [
            {
                "uses": "actions/checkout@v4",
                "with": {"submodules": True},
            },
            {
                "name": "Inject targets",
                "run": "cp -r edacation oss-cad-suite-build/",
            },
        ]

        job_dict: dict[str, object] = {
            "runs-on": "ubuntu-latest",
            "steps": steps,
        }
        if deps:
            job_dict["needs"] = deps[0] if len(deps) == 1 else deps

        if not job.is_top_package:
            steps.append(
                {
                    "name": "Cache sources",
                    "uses": "actions/cache@v4",
                    "with": {
                        "path": "oss-cad-suite-build/_sources",
                        "key": f"cache-sources-{job.target}",
                    },
                }
            )

        _append_download_and_extract_steps(steps, job, available)

        if job.is_top_package:
            short_target = job.target.removesuffix("-full")
            steps.extend(
                [
                    {
                        "name": "Build",
                        "run": (
                            "cd oss-cad-suite-build/\n"
                            f"./builder.py build --rules=default,edacation --arch={job.arch} "
                            f"--target={job.target} --single"
                        ),
                    },
                    {
                        "name": "Tar build output",
                        "env": {
                            "tooldir": f"oss-cad-suite-build/_outputs/{job.arch}/{job.target}",
                        },
                        "run": (
                            f"cp ${{tooldir}}/.hash ${{tooldir}}/{job.target}/.hash\n"
                            f"tar -C ${{tooldir}}/{job.target} -czf {job.arch}-{short_target}.tgz ."
                        ),
                    },
                    {
                        "name": "Upload artifact",
                        "uses": "actions/upload-artifact@v4",
                        "with": {
                            "name": job.name,
                            "path": f"{job.arch}-{short_target}.tgz",
                        },
                    },
                ]
            )
        else:
            steps.extend(
                [
                    {
                        "name": "Build",
                        "run": (
                            "cd oss-cad-suite-build/\n"
                            f"./builder.py build --rules=default,edacation --arch={job.arch} "
                            f"--target={job.target} --single --tar"
                        ),
                    },
                    {
                        "name": "Upload artifact",
                        "uses": "actions/upload-artifact@v4",
                        "with": {
                            "name": job.name,
                            "path": f"oss-cad-suite-build/{job.name}.tgz",
                        },
                    },
                ]
            )

        jobs_section[job.name] = job_dict

    jobs_section["package"] = {
        "runs-on": "ubuntu-latest",
        "needs": full_roots,
        "steps": [
            {
                "uses": "actions/checkout@v4",
                "with": {"submodules": True},
            },
            {
                "name": "Download target artifacts",
                "uses": "actions/download-artifact@v4",
                "with": {
                    "path": "_tools/",
                    "pattern": "*-full",
                    "merge-multiple": True,
                },
            },
            {
                "name": "Extract artifacts",
                "run": (
                    "cd _tools/\n"
                    "for file in *.tgz; do\n"
                    '  echo "Extracting ${file}..."\n'
                    '  tar -xzf "$file" --one-top-level\n'
                    '  rm "$file"\n'
                    "done"
                ),
            },
            {
                "name": "Package tools",
                "env": {"PYTHONUNBUFFERED": "1"},
                "run": "./package.py --in-dir=_tools/ --out-dir=_outputs/ --report tools.json",
            },
            {
                "name": "Get release version",
                "id": "version",
                "run": "echo \"version=$(jq -r '.version' tools.json)\" >> $GITHUB_OUTPUT",
            },
            {
                "name": "Release tools",
                "uses": "softprops/action-gh-release@v2",
                "with": {
                    "tag_name": "${{ steps.version.outputs.version }}",
                    "files": "_outputs/*\ntools.json",
                },
            },
        ],
    }

    return yaml.safe_dump(workflow, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate .github/workflows/build.yml by combining per-arch/target "
            "output from oss-cad-suite-build/builder.py ci."
        )
    )
    _ = parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to native-fpga-tools repository root (default: current directory).",
    )
    _ = parser.add_argument(
        "--output",
        default=".github/workflows/build.yml",
        help="Output workflow path, relative to repo root.",
    )
    _ = parser.add_argument(
        "--rules",
        default="default,edacation",
        help="Rules passed to builder.py ci/build.",
    )
    _ = parser.add_argument(
        "--arches",
        default=",".join(DEFAULT_ARCHES),
        help="Comma-separated architecture list.",
    )
    _ = parser.add_argument(
        "--targets",
        default=",".join(DEFAULT_TARGETS),
        help="Comma-separated top-package targets without '-full'.",
    )
    _ = parser.add_argument(
        "--cron",
        default="0 1 * * *",
        help="Cron expression for scheduled workflow run.",
    )

    args = parser.parse_args(namespace=Args())

    repo_root = Path(str(args.repo_root)).resolve()
    builder_dir = repo_root / "oss-cad-suite-build"
    output_path = repo_root / str(args.output)

    if not builder_dir.joinpath("builder.py").exists():
        raise FileNotFoundError(f"Cannot find builder.py in {builder_dir}")

    arches = [x.strip() for x in str(args.arches).split(",") if x.strip()]
    targets = [x.strip() for x in str(args.targets).split(",") if x.strip()]
    if not arches or not targets:
        raise ValueError("At least one architecture and one target must be specified")

    generated_job_sets: list[dict[str, Job]] = []
    for arch in arches:
        for target in targets:
            top_target = f"{target}-full"
            yaml_text = run_ci_generation(
                builder_dir, arch, top_target, str(args.rules)
            )
            generated_job_sets.append(parse_generated_ci(yaml_text, arches))

    merged_jobs = merge_jobs(generated_job_sets)
    full_roots = [f"{arch}-{target}-full" for arch in arches for target in targets]

    required = compute_required_jobs(merged_jobs, full_roots)
    ordered = topological_order(merged_jobs, required)

    workflow_text = render_workflow(merged_jobs, ordered, full_roots, str(args.cron))

    os.makedirs(output_path.parent, exist_ok=True)
    _ = output_path.write_text(workflow_text)

    print(f"Generated {output_path} with {len(ordered)} build jobs + package job")


if __name__ == "__main__":
    main()
