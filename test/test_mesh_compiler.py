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

import wbe_build_utils_mesh_compiler
from wbe_build_utils_mesh_compiler import WBEMeshCompiler
from wbe_build_utils_mesh_compiler import _native


ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_MODEL_DIR = ROOT_DIR / "test-model"


def _cube_resource() -> dict[str, object]:
    return {
        "id": "cube",
        "type": "mesh",
        "path": "Cube/glTF/Cube.gltf",
        "graphics_pipeline_ids": ["main_pipeline"],
        "texture_output_dir": "textures",
    }


def test_package_imports() -> None:
    assert wbe_build_utils_mesh_compiler.WBEMeshCompiler is WBEMeshCompiler
    assert hasattr(_native, "compile_mesh")


def test_compiler_interface_compiles_cube(tmp_path: Path) -> None:
    compiler = WBEMeshCompiler()
    resource = _cube_resource()

    compiled = compiler.compile(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert isinstance(compiled, dict)
    assert compiled["id"] == "cube"
    assert compiled["type"] == "mesh"
    assert isinstance(compiled["submeshes"], list)
    assert compiled["submeshes"]

    submesh = compiled["submeshes"][0]
    assert submesh["id"] == "Cube"
    assert submesh["type"] == "submesh"
    assert submesh["material_id"] == "Cube"
    assert isinstance(submesh["vertices_data"], list)
    assert isinstance(submesh["indices_data"], list)
    assert submesh["vertices_data"]
    assert submesh["indices_data"]

    vertex = submesh["vertices_data"][0]
    assert set(vertex) == {"position", "uv", "normal", "bone_id"}
    assert set(vertex["position"]) == {"x", "y", "z"}
    assert set(vertex["uv"]) == {"u", "v"}
    assert set(vertex["normal"]) == {"x", "y", "z"}
    assert isinstance(vertex["position"]["x"], float)
    assert isinstance(vertex["uv"]["u"], float)
    assert isinstance(vertex["normal"]["x"], float)
    assert all(isinstance(index, int) for index in submesh["indices_data"])


def test_materials_compile_without_absolute_paths(tmp_path: Path) -> None:
    compiler = WBEMeshCompiler()
    resource = _cube_resource()

    materials = compiler.compile_materials(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert isinstance(materials, list)
    assert materials
    material = materials[0]
    assert material["id"] == "Cube"
    assert material["type"] == "material"
    assert material["graphics_pipeline_ids"] == ["main_pipeline"]
    assert isinstance(material["textures"], list)
    assert material["textures"]

    texture_keys = {texture["texture_key"] for texture in material["textures"]}
    assert "base_color" in texture_keys
    assert "roughness_metallic_ao" in texture_keys
    for texture_binding in material["textures"]:
        texture = texture_binding["texture"]
        assert texture["type"] == "image"
        assert not Path(texture["path"]).is_absolute()
        assert texture["color_space"] in {"srgb", "linear"}
        assert texture["channel_count"] in {3, 4}
