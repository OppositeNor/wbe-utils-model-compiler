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

class WBEFieldMetadata(BaseModel):
    """Field metadata.

    Attributes: 
        field_name: The name of the field.
        field_type: The type of the field.
    """
    attribute : list[str] = Field(default_factory=list)
    name : str = ""
    type : str = ""

class WBEMethodMetadata(BaseModel):
    """Method metadata.

    Attributes: 
        method_name: The name of the method.
        args_name: The name of the arguments.
        args_type: The types of the arguments.
        ret_type: The return type.
    """
    attribute : list[str] = Field(default_factory=list)
    method_name : str = ""
    name : list[str] = Field(default_factory=list)
    type : list[str] = Field(default_factory=list)
    ret_type : str = ""

class WBEClassMetadata(BaseModel):
    """Class metadata.

    Attributes: 
        is_struct: Is it declared as struct.
        class_name: The name of the class.
        fields: The fields of the class.
        methods: The methods of the class.
    """
    is_struct : bool = False
    in_header : str = ""
    name : str = ""
    extended_parents : list[Any] = Field(default_factory=list[Any])
    attribute : list[str] = Field(default_factory=list[str])
    fields : list[WBEFieldMetadata] = Field(default_factory=list[WBEFieldMetadata])
    methods : list[WBEMethodMetadata] = Field(default_factory=list[WBEMethodMetadata])

class WBELabelMetadata(BaseModel):
    """Label metadata.

    Attributes: 
        attribute: The attribute of the label.
        label_name: The name of the label.
    """
    attribute : list[str] = Field(default_factory=list[str])
    name : str = ""

class WBEFileMetadata(BaseModel):
    """Metadata in a single C++ file.

    Attributes: 
        file_path: The path of the file.
        hashcode: The hashcode of the file's content.
        deps: The dependencies of the file. Usually from include or import module.
        labels: The registered labels metadata.
        classes: The registered classes metadata.
    """
    file_path : str = ""
    hashcode : str = ""
    deps : list[str] = Field(default_factory=list)
    labels : list[WBELabelMetadata] = Field(default_factory=list)
    classes : list[WBEClassMetadata] = Field(default_factory=list)

class WBEMetadata(BaseModel):
    """Metadata.

    Attributes:
        labels: The registrated lables.
        classes: The registrated classes.
    """
    labels : list[WBELabelMetadata] = Field(default_factory=list[WBELabelMetadata])
    classes : list[WBEClassMetadata] = Field(default_factory=list[WBEClassMetadata])

    def sort(self) -> None:
        """Sor the fields. This may gurantee the order it generates will always be the same,
        which is usefull not triggering the CMake and metaparser's compilation for the generated
        files.
        """
        self.labels = sorted(self.labels, key=lambda label: label.name)
        self.classes = sorted(self.classes, key=lambda cxx_class: cxx_class.name)
