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

from pathlib import Path
import os
import shutil
import subprocess

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


ROOT_DIR = Path(__file__).resolve().parent

# The path declared in the White Bird Engine project. Not really ideal to write it this way, but since we allow
# setting this up with environment variables I suppose this is OK.
DEFAULT_ASSIMP_ROOT = ROOT_DIR.parent / "assimp"

README_PATH = ROOT_DIR / "README.md"


class CMakeExtension(Extension):
    def __init__(self, p_name: str) -> None:
        super().__init__(p_name, sources=[])


class CMakeBuild(build_ext):
    def run(self) -> None:
        if shutil.which("cmake") is None:
            raise RuntimeError("CMake is required to build the native model compiler extension.")
        super().run()

    def build_extension(self, p_extension: Extension) -> None:
        extension_output_dir = Path(self.get_ext_fullpath(p_extension.name)).parent.resolve()
        build_temp = Path(self.build_temp) / p_extension.name
        build_temp.mkdir(parents=True, exist_ok=True)
        build_type = "Debug" if self.debug else "Release"
        assimp_root = Path(os.environ.get("WBE_ASSIMP_ROOT", DEFAULT_ASSIMP_ROOT))

        configure_command = [
            "cmake",
            "-S",
            str(ROOT_DIR),
            "-B",
            str(build_temp),
            f"-DCMAKE_BUILD_TYPE={build_type}",
            f"-DPYTHON_EXTENSION_OUTPUT_DIRECTORY={extension_output_dir}",
            f"-DWBE_ASSIMP_ROOT={assimp_root.resolve()}",
        ]
        subprocess.check_call(configure_command, cwd=ROOT_DIR)

        build_command = ["cmake", "--build", str(build_temp), "--target", "_native"]
        cpu_count = os.cpu_count()
        if cpu_count is not None:
            build_command.extend(["-j", str(cpu_count)])
        subprocess.check_call(build_command, cwd=ROOT_DIR)


setup(
    name="wbe-utils-model-compiler",
    version="0.1.0",
    description="White Bird Engine mesh resource compiler.",
    long_description=README_PATH.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=["wbe_utils_model_compiler"],
    ext_modules=[CMakeExtension("wbe_utils_model_compiler._native")],
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
    python_requires=">=3.10",
)
