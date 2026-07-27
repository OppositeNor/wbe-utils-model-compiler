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
import os
from pathlib import Path
from build_script.utils import list_files

target_info = {
    "debug" : {
        "c-compiler" : "clang",
        "cpp-compiler" : "clang++",
        "export-directory" : "debug",
        "cmake-build-type" : "Debug",
        "build-shared" : True,
        "generate-tests" : True,
    },
    "release" : {
        "c-compiler" : "clang",
        "cpp-compiler" : "clang++",
        "export-directory" : "release",
        "cmake-build-type" : "Release",
        "build-shared" : True,
        "generate-tests" : True,
    },
    "debug-ninja" : {
        "c-compiler" : "clang",
        "cpp-compiler" : "clang++",
        "export-directory" : "debug",
        "cmake-build-type" : "Debug",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : True,
    },
    "release-ninja" : {
        "c-compiler" : "clang",
        "cpp-compiler" : "clang++",
        "export-directory" : "release",
        "cmake-build-type" : "Release",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : True,
    },
    "deploy" : {
        "c-compiler" : "clang",
        "cpp-compiler" : "clang++",
        "export-directory" : "deploy",
        "cmake-build-type" : "Deploy",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : False,
    },
    "debug-gcc" : {
        "c-compiler" : "gcc",
        "cpp-compiler" : "g++",
        "export-directory" : "debug-gcc",
        "build-shared" : True,
        "cmake-build-type" : "Debug",
        "generate-tests" : True,
    },
    "release-gcc" : {
        "c-compiler" : "gcc",
        "cpp-compiler" : "g++",
        "export-directory" : "release-gcc",
        "cmake-build-type" : "Release",
        "build-shared" : True,
        "generate-tests" : True,
    },
    "debug-gcc-ninja" : {
        "c-compiler" : "gcc",
        "cpp-compiler" : "g++",
        "export-directory" : "debug-gcc",
        "cmake-build-type" : "Debug",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : True,
    },
    "release-gcc-ninja" : {
        "c-compiler" : "gcc",
        "cpp-compiler" : "g++",
        "export-directory" : "release-gcc",
        "cmake-build-type" : "Release",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : True,
    },
    "deploy-gcc" : {
        "c-compiler" : "gcc",
        "cpp-compiler" : "g++",
        "export-directory" : "deploy-gcc",
        "cmake-build-type" : "Deploy",
        "build-shared" : True,
        "generator" : "Ninja",
        "generate-tests" : False,
    },
}

default_target = "deploy"

header_extensions = set([".hh"])
src_extensions = set([".cpp"])
source_extensions = src_extensions.union(header_extensions)
include_dir = "include"
source_dir = "src"
test_dir = "tests"
test_env_res_dir = "test_env_res"
test_env_dir = "test_env"

gen_info = {
    # Utilize this for code generation.
}

gen_info["static_serializables"].extend(gen_info["serializables"])

# Setup directories
root_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

project_files = list_files(root_dir, ignore_dirs=["dependencies", "generated",
                                                  ".cache", ".git", ".github", "__pycache__",
                                                  "build"])
project_sources = [path for path in project_files if Path(path).suffix in source_extensions]
project_headers = [path for path in project_sources if Path(path).suffix in header_extensions]
project_files_exclude_tests = list_files(root_dir, ignore_dirs=["tests", "dependencies", "generated",
                                                                ".cache", ".git", ".github", "__pycache__",
                                                                "build"])
project_sources_exclude_tests = [path for path in project_files_exclude_tests if Path(path).suffix in source_extensions]
project_headers_exclude_tests = [path for path in project_sources_exclude_tests if Path(path).suffix in header_extensions]
gen_info_files = list_files(root_dir, ignore_dirs=[".cache", ".git",
                                                   ".github", "__pycache__", "build"])
gen_info_files = [gen_info for gen_info in gen_info_files if os.path.basename(gen_info) == "generate.json"]

