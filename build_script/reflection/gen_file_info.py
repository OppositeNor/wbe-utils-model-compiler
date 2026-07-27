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
from typing import Any
from pydantic import BaseModel, Field


class WBEGenFileInfo(BaseModel):
    """Information of a generated file.

    Attributes:
        output_name: The name of the output file.
        template: The name of the template file.
        out_dir: The directory to output to.
        params: Per-entry parameter dict. Values declared here override all
                other sources when resolving ${name} patterns in this entry's
                output_name, template, out_dir, and data fields.
        data: The data that's passed into the generation. If any attribute starts with a '.',
              the attribute will be replaced by the "attributes" parameter in the code generator.
              Available ones are:
              metadata: The metadata of the project files.
    """
    output_name : str = Field(default_factory=str)
    template : str = Field(default_factory=str)
    out_dir : str = Field(default_factory=str)
    params : dict[str, str] = Field(default_factory=dict)
    data : dict[str, Any] = Field(default_factory=dict[str, Any])
