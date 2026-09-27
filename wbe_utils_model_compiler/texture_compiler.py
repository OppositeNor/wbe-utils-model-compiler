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

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TextureCompileRequest:
    """One sampled-texture conversion; thread_count bounds internal encoder parallelism when specified."""

    source_path: Path
    destination_path: Path
    source_format: str
    target_format: str
    generate_mipmap: bool
    flip_h: bool = False
    flip_v: bool = False
    thread_count: int | None = None


@runtime_checkable
class TextureCompiler(Protocol):
    """Interface implemented by the host asset-conditioning pipeline."""

    def compile_texture(self, p_request: TextureCompileRequest) -> None:
        """Compile one texture. Calls may overlap for distinct destinations; honor thread_count when provided."""

