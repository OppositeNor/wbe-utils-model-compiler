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
import hashlib
from pathlib import Path

def to_uint32(x: int) -> int:
    """Convert a uint64 integer to uint32 to match the usage in the C++ file.

    Args:
        x: The value to be converted.

    Returns:
        The converted value.
    """
    return x & 0xFFFFFFFF

def hash_str(str_input : str) -> int:
    """Hash a string.

    Args:
        str_input: The string to hash.

    Returns:
        The hash value of the string.
    """
    if (len(str_input) != 0):
        return to_uint32(ord(str_input[0]) + to_uint32(33 * hash_str(str_input[1:])))
    else:
        return 5381

def hash_file(path : str) -> str:
    """Hash a file.

    Args:
        path: The path to the file to get the hashcode.

    Returns: The hashcode of the file's content.
        
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def hash_str_sha256(str_input : str) -> str:
    """Hash a string with sha256, has smaller collision posibility compared to hash_str method.

    Args:
        str_input: The string to be hashed.

    Returns:
        The hashed result.
    """
    hasher = hashlib.sha256()
    hasher.update(str_input.encode("utf-8"))
    return hasher.hexdigest()

def list_files(dir: str | Path, ignore_dirs: list[str] | None = None) -> list[str]:
    """List all the file in a directory (recursivly).

    Args:
        dir: The directory to list.
        ignore_dirs: The directories to ignore.
    """
    root = Path(dir)
    ignore_set: set[str] = set(ignore_dirs or [])
    result: list[str] = []
    for path in root.rglob('*'):
        # Skip directories.
        # If any of the parent directories are ignored, ignore.
        if any(ignored in path.parts for ignored in ignore_set):
            continue
        if not path.is_dir():
            result.append(str(path))
    return result
