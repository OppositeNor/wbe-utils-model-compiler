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

import wbe_utils_model_compiler
from wbe_utils_model_compiler import WBEModelCompiler
from wbe_utils_model_compiler import _native


ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_MODEL_DIR = ROOT_DIR / "test-model"


def _cube_resource() -> dict[str, object]:
    return {
        "id": "cube",
        "type": "model",
        "file": "Cube/glTF/Cube.gltf",
        "graphics_pipeline_ids": ["main_pipeline"],
        "texture_output_dir": "textures",
    }


def test_package_imports() -> None:
    assert wbe_utils_model_compiler.WBEModelCompiler is WBEModelCompiler
    assert hasattr(_native, "compile_mesh")


def test_compiler_interface_compiles_cube(tmp_path: Path) -> None:
    compiler = WBEModelCompiler()
    resource = _cube_resource()

    compiled = compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert isinstance(compiled, dict)
    assert compiled["id"] == "cube.mesh"
    assert compiled["type"] == "mesh"
    assert isinstance(compiled["submeshes"], list)
    assert compiled["submeshes"]

    submesh = compiled["submeshes"][0]
    assert submesh["id"] == "cube.submesh.Cube"
    assert submesh["type"] == "submesh"
    assert submesh["material_id"] == "cube.material.Cube"
    assert "vertices_data" not in submesh
    assert "indices_data" not in submesh
    assert isinstance(submesh["geometry_path"], str)
    assert isinstance(submesh["geometry_sections"], list)
    geometry_path = tmp_path / submesh["geometry_path"]
    assert geometry_path.is_file()

    sections = {section["slot"]: section for section in submesh["geometry_sections"]}
    assert set(sections) == {"position", "normal", "tangent", "bitangent", "uv", "index"}
    assert sections["position"]["type"] == "vec3"
    assert sections["normal"]["type"] == "vec3"
    assert sections["tangent"]["type"] == "vec3"
    assert sections["bitangent"]["type"] == "vec3"
    assert sections["uv"]["type"] == "vec2"
    assert sections["index"]["type"] == "uint32"
    file_size = geometry_path.stat().st_size
    for section in sections.values():
        assert isinstance(section["start"], int)
        assert isinstance(section["size"], int)
        assert section["size"] > 0
        assert section["start"] + section["size"] <= file_size
    assert sections["position"]["size"] % (3 * 4) == 0
    assert sections["uv"]["size"] % (2 * 4) == 0
    assert sections["index"]["size"] % (3 * 4) == 0


def test_materials_compile_without_absolute_paths(tmp_path: Path) -> None:
    compiler = WBEModelCompiler()
    resource = _cube_resource()

    materials = compiler.compile_materials(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert isinstance(materials, list)
    assert materials
    material = materials[0]
    assert material["id"] == "cube.material.Cube"
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
        assert not Path(texture["file"]).is_absolute()
        assert "path" in texture
        assert not Path(texture["path"]).is_absolute()
        assert texture["color_space"] in {"srgb", "rgb"}
        assert texture["channel_count"] in {3, 4}
