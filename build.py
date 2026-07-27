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
import json
import os
from pathlib import Path
import subprocess
import traceback
from typing import Any
from build_script import on_build
import shutil
import build_config
from build_script.reflection.code_gen import WBEGenFileInfo
import build_setup

metaparser_clang_args: list[str] = [
    "-std=c++20",
    f"-I{build_setup.include_dir}",
    f"-I{build_setup.per_target_include_dir}",
    "-DWBE_REFLECTION_PARSER"
]

# HELPER FUNCTIONS
def _get_cmake_command_from_info(build_info: dict[str, Any]) -> list[str]:
    """Helper function which converts the build info to cmake command"""
    result: list[str] = ["cmake"]
    result.append("-B")
    result.append(build_setup.build_dir)
    result.append(f"-DWBE_BINARY_DIR={build_setup.binary_dir}")
    result.append(f"-DWBE_BUILD_SHARED={"ON" if build_info["build-shared"] else "OFF"}")
    if build_info.get("generator") is not None:
        result.append("-G")
        result.append(build_info["generator"])
    result.append(f"-DCMAKE_BUILD_TYPE={build_info["cmake-build-type"]}")
    result.append(f"-DWBE_BUILD_TARGET={build_setup.args.target}")
    result.append(f"-DWBE_INCLUDE_DIR={build_setup.include_dir}")
    result.append(f"-DWBE_PER_TARGET_INCLUDE_DIR={build_setup.per_target_include_dir}")
    if build_info.get("cpp-compiler") is not None:
        result.append(f"-DCMAKE_CXX_COMPILER={build_info["cpp-compiler"]}")
    if build_info.get("c-compiler") is not None:
        result.append(f"-DCMAKE_C_COMPILER={build_info["c-compiler"]}")
    if build_info["generate-tests"]:
        result.append("-DWBE_MAKE_TEST=ON")
    else:
        result.append("-DWBE_MAKE_TEST=OFF")
    if build_info.get("additional-cmake-args") is not None:
        result.append(build_info["additional-cmake-args"])
    return result

def _gather_license() -> None:
    # Get white bird engine license
    shutil.copyfile(os.path.join(build_setup.root_dir, "LICENSE"), os.path.join(build_setup.licenses_output_dir, "white-bird-engine_LICENSE"))
    # Get licenses from dependencies
    deps_dir = Path(build_setup.dependencies_dir).resolve()
    output_dir = Path(build_setup.licenses_output_dir).resolve()

    for subdir in deps_dir.iterdir():
        if subdir.is_dir():
            license_files = [p for p in subdir.iterdir() 
                             if p.is_file() and ("license" in p.name.lower() or
                                                 "copying" in p.name.lower() or
                                                 "authors" in p.name.lower() or
                                                 "patents" in p.name.lower())]
            if not license_files:
                print(f"Warning: No LICENSE found in {subdir}")
                continue
            for lf in license_files:
                target_name = f"{subdir.name}_{lf.name}"
                target_path = os.path.join(output_dir, target_name)
                shutil.copy2(lf, target_path)

            # Apache license requires to also include a NOTICE file if exists:
            notice_files = [p for p in subdir.iterdir()
                if p.is_file() and "notice" in p.name.lower()]
            if notice_files:
                for nf in notice_files:
                    target_name = f"{subdir.name}_{nf.name}"
                    target_path = os.path.join(output_dir, target_name)
                    print(f"Copying NOTICE {nf} -> {target_path}")
                    shutil.copy2(nf, target_path)

def _gather_gen_infos() -> list[WBEGenFileInfo]:
    gen_infos: list[WBEGenFileInfo] = []
    for gen_info_file in build_config.gen_info_files:
        with open(gen_info_file) as f:
            data = json.load(f)
        file_infos = [WBEGenFileInfo(**info) for info in data]
        for file_info in file_infos:
            if not file_info.out_dir:
                file_info.out_dir = os.path.dirname(gen_info_file)
        gen_infos.extend(file_infos)
    return gen_infos

# ENTRY
if __name__ == "__main__":
    # Gather sources for reflection
    try:
        print(f"WBEBuilder: Building target: {build_setup.args.target}.")
        print("WBEBuilder: Running asset conditioning pipeline...")
        print("WBEBuilder: Gathering licenses...")
        _gather_license()
        print("WBEBuilder: Gathering sources...")
        if build_setup.build_target["generate-tests"]:
            headers = build_config.project_headers
        else:
            headers = build_config.project_headers_exclude_tests
        print("WBEBuilder: Gathering generate.json...")
        gen_infos = _gather_gen_infos()

        # Run reflection script
        print("WBEBuilder: Running reflections...")
        on_build.reflect(metaparser_clang_args, build_setup.metadata_path, build_setup.metadata_cache_dir, headers, gen_infos)

        # Build project with CMake
        print("WBEBuilder: Running cmake...")
        result = subprocess.run(_get_cmake_command_from_info(build_setup.build_target))
        if result.returncode != 0:
            raise RuntimeError("Failed to setup cmake build.")
        build_command = ["cmake", "--build", build_setup.build_dir]
        if os.cpu_count() is not None:
            build_command.extend(["-j", str(os.cpu_count())])
        result = subprocess.run(build_command)
        if result.returncode != 0:
            raise RuntimeError("Failed to build with CMake.")

        # Keep compile database available in both conventional locations used by tooling.
        compile_commands_path = os.path.join(build_setup.build_dir, "compile_commands.json")
        shutil.copy(compile_commands_path, "build")
        shutil.copy(compile_commands_path, "compile_commands.json")
        print("WBEBuilder: Finished!")

    except Exception as e:
        print("Build failed! Message:", e)
        traceback.print_exc()
        exit(-1)
