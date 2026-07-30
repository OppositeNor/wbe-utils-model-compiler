# Copyright 2025 OppositeNor
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_BUILD_TYPE = "Debug"
DEFAULT_ASSIMP_ROOT = ROOT_DIR.parent / "dependencies" / "assimp"


def _run(command: list[str], p_cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=p_cwd if p_cwd is not None else ROOT_DIR)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _build_dir(p_build_type: str) -> Path:
    return ROOT_DIR / "build" / p_build_type.lower()


def _is_configured(p_build_dir: Path) -> bool:
    return (p_build_dir / "CMakeCache.txt").exists() and ((p_build_dir / "Makefile").exists() or (p_build_dir / "build.ninja").exists())


def configure(p_build_type: str = DEFAULT_BUILD_TYPE, p_assimp_root: Path = DEFAULT_ASSIMP_ROOT) -> None:
    build_dir = _build_dir(p_build_type)
    build_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "cmake",
        "-S",
        str(ROOT_DIR),
        "-B",
        str(build_dir),
        f"-DCMAKE_BUILD_TYPE={p_build_type}",
        f"-DWBE_ASSIMP_ROOT={p_assimp_root.resolve()}",
    ]
    _run(command)


def build(p_build_type: str = DEFAULT_BUILD_TYPE, p_assimp_root: Path = DEFAULT_ASSIMP_ROOT) -> None:
    build_dir = _build_dir(p_build_type)
    if not _is_configured(build_dir):
        configure(p_build_type, p_assimp_root)
    command = ["cmake", "--build", str(build_dir)]
    cpu_count = os.cpu_count()
    if cpu_count is not None:
        command.extend(["-j", str(cpu_count)])
    _run(command)


def test(p_build_type: str = DEFAULT_BUILD_TYPE, p_assimp_root: Path = DEFAULT_ASSIMP_ROOT) -> None:
    build(p_build_type, p_assimp_root)
    _run([sys.executable, "-m", "pytest", str(ROOT_DIR / "test")], ROOT_DIR)


def clean() -> None:
    shutil.rmtree(ROOT_DIR / "build", ignore_errors=True)
    shutil.rmtree(ROOT_DIR / "dist", ignore_errors=True)
    for path in ROOT_DIR.glob("*.egg-info"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in (ROOT_DIR / "wbe_utils_model_compiler").glob("_native*.so"):
        if path.is_file():
            path.unlink()
    for path in ROOT_DIR.glob("**/__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in ROOT_DIR.glob("**/.pytest_cache"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the White Bird Engine model compiler.")
    parser.add_argument("operation", choices=["configure", "build", "test", "clean"], help="Build operation to run.")
    parser.add_argument("--build-type", default=DEFAULT_BUILD_TYPE, help="CMake build type.")
    parser.add_argument(
        "--assimp-root",
        type=Path,
        default=Path(os.environ.get("WBE_ASSIMP_ROOT", DEFAULT_ASSIMP_ROOT)),
        help="Path to the Assimp source directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.operation == "configure":
        configure(args.build_type, args.assimp_root)
    elif args.operation == "build":
        build(args.build_type, args.assimp_root)
    elif args.operation == "test":
        test(args.build_type, args.assimp_root)
    elif args.operation == "clean":
        clean()


if __name__ == "__main__":
    main()
