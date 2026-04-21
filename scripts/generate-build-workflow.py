#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import os
import re
import subprocess
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


def parse_generated_ci(yaml_text: str) -> dict[str, dict[str, object]]:
    loaded_obj = cast(object, yaml.safe_load(_extract_yaml_document(yaml_text)))
    if not isinstance(loaded_obj, dict):
        raise ValueError("Generated YAML does not contain a jobs section")

    loaded_dict = cast(dict[object, object], loaded_obj)
    jobs_raw_obj = loaded_dict.get("jobs")
    if jobs_raw_obj is None:
        raise ValueError("Generated YAML does not contain a jobs section")

    if not isinstance(jobs_raw_obj, dict):
        raise ValueError("Generated YAML jobs section is malformed")
    jobs_raw_dict = cast(dict[object, object], jobs_raw_obj)

    jobs: dict[str, dict[str, object]] = {}

    for name_obj, job_obj in jobs_raw_dict.items():
        if not isinstance(name_obj, str):
            continue
        if not isinstance(job_obj, dict):
            continue
        job_obj_dict = cast(dict[object, object], job_obj)
        jobs[name_obj] = cast(dict[str, object], copy.deepcopy(job_obj_dict))

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


def merge_jobs(
    job_sets: list[dict[str, dict[str, object]]],
) -> dict[str, dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}

    for jobs in job_sets:
        for name, job_dict in jobs.items():
            if name not in merged:
                merged[name] = copy.deepcopy(job_dict)

    return merged


def _prefix_hashfiles_paths(condition: str) -> str:
    pattern = re.compile(r"hashFiles\('([^']+)'\)")

    def repl(match: re.Match[str]) -> str:
        path = match.group(1)
        if path.startswith("oss-cad-suite-build/"):
            return match.group(0)
        return f"hashFiles('oss-cad-suite-build/{path}')"

    return pattern.sub(repl, condition)


def _transform_release_paths(job_dict: dict[object, object]) -> None:
    if_expr = job_dict.get("if")
    if isinstance(if_expr, str):
        # Transform: make hashFiles paths match the workspace layout.
        job_dict["if"] = _prefix_hashfiles_paths(if_expr)

    with_obj = job_dict.get("with")
    if not isinstance(with_obj, dict):
        return
    with_dict = cast(dict[object, object], with_obj)

    artifacts = with_dict.get("artifacts")
    if isinstance(artifacts, str) and not artifacts.startswith("oss-cad-suite-build/"):
        # Transform: release-action artifact path is relative to repo root in our workflow.
        with_dict["artifacts"] = f"oss-cad-suite-build/{artifacts}"


def _adapt_upstream_job(
    job_dict: dict[str, object], inject_targets_step: dict[object, object]
) -> dict[str, object]:
    job_dict = copy.deepcopy(job_dict)

    steps_obj = job_dict.get("steps")
    if not isinstance(steps_obj, list):
        raise ValueError("Upstream job has malformed steps")
    steps = cast(list[object], steps_obj)

    insertion_index = 1
    checkout_index = -1
    for i, step_obj in enumerate(steps):
        if not isinstance(step_obj, dict):
            continue
        step = cast(dict[object, object], step_obj)
        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/checkout@"):
            insertion_index = i + 1
            checkout_index = i
            break

    # Transform: inject local rules into upstream builder tree.
    steps.insert(insertion_index, copy.deepcopy(inject_targets_step))

    # Transform: run upstream shell steps from the builder submodule directory.
    job_dict["defaults"] = {
        "run": {
            "working-directory": "oss-cad-suite-build",
        }
    }

    for step_obj in steps:
        if not isinstance(step_obj, dict):
            continue
        step = cast(dict[object, object], step_obj)

        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/checkout@"):
            with_obj_checkout = step.get("with")
            if isinstance(with_obj_checkout, dict):
                with_checkout = cast(dict[object, object], with_obj_checkout)
            else:
                with_checkout = {}
            # Transform: ensure submodule checkout so builder.py and sources are present.
            with_checkout["submodules"] = True
            step["with"] = with_checkout

        with_obj = step.get("with")
        if (
            isinstance(uses, str)
            and uses.startswith("actions/cache@")
            and isinstance(with_obj, dict)
        ):
            with_dict = cast(dict[object, object], with_obj)
            cache_path = with_dict.get("path")
            if isinstance(cache_path, str) and not cache_path.startswith(
                "oss-cad-suite-build/"
            ):
                # Transform: cache path must point into submodule working tree.
                with_dict["path"] = f"oss-cad-suite-build/{cache_path}"

        if isinstance(uses, str) and uses.startswith("ncipollo/release-action@"):
            # Transform: keep upstream release cache flow but normalize paths.
            _transform_release_paths(step)

    if checkout_index > 0:
        for step_obj in steps[:checkout_index]:
            if not isinstance(step_obj, dict):
                continue
            step = cast(dict[object, object], step_obj)
            run_cmd = step.get("run")
            if isinstance(run_cmd, str):
                # Transform: pre-checkout run steps cannot use builder working directory.
                step["working-directory"] = "."

    return job_dict


def _replace_top_package_publisher(
    job_dict: dict[str, object], job_name: str
) -> dict[str, object]:
    steps_obj = job_dict.get("steps")
    if not isinstance(steps_obj, list):
        raise ValueError(f"Top package job '{job_name}' has malformed steps")

    new_steps: list[object] = []
    for step_obj in cast(list[object], steps_obj):
        if isinstance(step_obj, dict):
            step = cast(dict[object, object], step_obj)
            uses = step.get("uses")
            if isinstance(uses, str) and uses.startswith("ncipollo/release-action@"):
                # Transform: top-level publish is centralized in final package job.
                continue
        new_steps.append(cast(object, step_obj))

    if not job_name.endswith("-full"):
        return job_dict
    short_name = job_name[: -len("-full")]
    last_dash = short_name.find("-")
    if last_dash <= 0:
        raise ValueError(f"Unexpected top-level job name format: {job_name}")
    arch = short_name[:last_dash]
    short_target = short_name[last_dash + 1 :]
    full_target = f"{short_target}-full"

    new_steps.extend(
        [
            {
                "name": "Tar build output",
                "env": {
                    "tooldir": f"_outputs/{arch}/{full_target}",
                },
                "run": (
                    f"cp ${{tooldir}}/.hash ${{tooldir}}/{full_target}/.hash\n"
                    f"tar -C ${{tooldir}}/{full_target} -czf {arch}-{short_target}.tgz ."
                ),
            },
            {
                "name": "Upload artifact",
                "uses": "actions/upload-artifact@v4",
                "with": {
                    "name": job_name,
                    "path": f"oss-cad-suite-build/{arch}-{short_target}.tgz",
                },
            },
        ]
    )
    # Transform: replace upstream release upload with artifact upload for package fan-in.
    job_dict["steps"] = new_steps

    return job_dict


def render_workflow(
    jobs: dict[str, dict[str, object]],
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

    inject_targets_step: dict[object, object] = {
        "name": "Inject targets",
        "run": "cp -r ../edacation .",
    }

    for job_name in jobs:
        job_dict = _adapt_upstream_job(jobs[job_name], inject_targets_step)
        if job_name.endswith("-full"):
            job_dict = _replace_top_package_publisher(job_dict, job_name)

        jobs_section[job_name] = job_dict

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

    generated_job_sets: list[dict[str, dict[str, object]]] = []
    for arch in arches:
        for target in targets:
            top_target = f"{target}-full"
            yaml_text = run_ci_generation(
                builder_dir, arch, top_target, str(args.rules)
            )
            generated_job_sets.append(parse_generated_ci(yaml_text))

    merged_jobs = merge_jobs(generated_job_sets)
    full_roots = [f"{arch}-{target}-full" for arch in arches for target in targets]

    full_roots_existing = [name for name in full_roots if name in merged_jobs]
    if not full_roots_existing:
        raise ValueError("No top-level '-full' jobs found in merged upstream CI output")

    workflow_text = render_workflow(merged_jobs, full_roots_existing, str(args.cron))

    os.makedirs(output_path.parent, exist_ok=True)
    _ = output_path.write_text(workflow_text)

    print(
        f"Generated {output_path} with {len(merged_jobs)} upstream jobs + package job"
    )


if __name__ == "__main__":
    main()
