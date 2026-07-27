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

from argparse import ArgumentParser
import os
import sys
import build_config

# SETUP
print("WBEBuilder: Setting up...")
# Parse CLA
arg_parser = ArgumentParser(
    prog=sys.argv[0],
    description="Build script to build White Bird Engine."
)
arg_parser.add_argument("-t", "--target", help="Build target.", choices=list(build_config.target_info.keys()), default=build_config.default_target)
args = arg_parser.parse_args()

build_target = build_config.target_info[args.target]

# Sources dirs
root_dir = build_config.root_dir
include_dir = os.path.join(root_dir, build_config.include_dir)
source_dir = os.path.join(root_dir, build_config.source_dir)
per_target_include_dir = os.path.join(include_dir, "per_target", args.target)
test_dir = os.path.join(root_dir, build_config.test_dir)
test_env_dir = os.path.join(root_dir, build_config.test_env_dir)
build_root_dir = os.path.join(root_dir, "build")
build_dir = os.path.join(build_root_dir, build_target["export-directory"])
binary_dir = os.path.join(build_dir, "bin")
dependencies_dir = os.path.join(root_dir, "dependencies")
template_dir = os.path.join(root_dir, "templates")
# Resource dirs
metadata_cache_dir = os.path.join(build_dir, "metadata_cache")

# Create directories
os.makedirs(metadata_cache_dir, exist_ok=True)

