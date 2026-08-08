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
import struct

import pytest
import wbe_utils_model_compiler
from wbe_utils_model_compiler import WBEUtilsModelCompiler
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


def _section_data(geometry_path: Path, submesh: dict[str, object], slot: str) -> bytes:
    sections = submesh["geometry_sections"]
    assert isinstance(sections, list)
    section = next(section for section in sections if section["slot"] == slot)
    data = geometry_path.read_bytes()
    start = section["start"]
    size = section["size"]
    return data[start:start + size]


def _vec3_section(geometry_path: Path, submesh: dict[str, object], slot: str) -> list[tuple[float, float, float]]:
    return list(struct.iter_unpack("<fff", _section_data(geometry_path, submesh, slot)))


def _index_section(geometry_path: Path, submesh: dict[str, object]) -> list[int]:
    return [value[0] for value in struct.iter_unpack("<I", _section_data(geometry_path, submesh, "index"))]


def test_package_imports() -> None:
    assert wbe_utils_model_compiler.WBEUtilsModelCompiler is WBEUtilsModelCompiler
    assert hasattr(_native, "compile_mesh")


def test_compiler_interface_compiles_cube(tmp_path: Path) -> None:
    compiler = WBEUtilsModelCompiler()
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
    assert submesh["geometry_path"] == "cube.mesh.geometry.bin"
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


def test_mesh_compilation_scales_positions_and_converts_between_coordinate_spaces(tmp_path: Path) -> None:
    compiler = WBEUtilsModelCompiler()
    baseline_output_dir = tmp_path / "baseline"
    converted_output_dir = tmp_path / "converted"
    baseline = compiler.compile_mesh(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, baseline_output_dir)
    resource = {
        **_cube_resource(),
        "scale_vertex_pos": 2.5,
        "source_space": {"up": "+z", "right": "+x", "front": "-y"},
        "target_space": {"up": "+y", "right": "-z", "front": "-x"},
    }
    converted = compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, converted_output_dir)

    baseline_submesh = baseline["submeshes"][0]
    converted_submesh = converted["submeshes"][0]
    baseline_path = baseline_output_dir / baseline_submesh["geometry_path"]
    converted_path = converted_output_dir / converted_submesh["geometry_path"]

    baseline_positions = _vec3_section(baseline_path, baseline_submesh, "position")
    converted_positions = _vec3_section(converted_path, converted_submesh, "position")
    for baseline_position, converted_position in zip(baseline_positions, converted_positions, strict=True):
        expected = (baseline_position[1] * 2.5, baseline_position[2] * 2.5, -baseline_position[0] * 2.5)
        assert converted_position == pytest.approx(expected)

    for slot in ("normal", "tangent", "bitangent"):
        baseline_vectors = _vec3_section(baseline_path, baseline_submesh, slot)
        converted_vectors = _vec3_section(converted_path, converted_submesh, slot)
        for baseline_vector, converted_vector in zip(baseline_vectors, converted_vectors, strict=True):
            assert converted_vector == pytest.approx((baseline_vector[1], baseline_vector[2], -baseline_vector[0]))

    baseline_indices = _index_section(baseline_path, baseline_submesh)
    converted_indices = _index_section(converted_path, converted_submesh)
    expected_indices: list[int] = []
    for index in range(0, len(baseline_indices), 3):
        expected_indices.extend((baseline_indices[index], baseline_indices[index + 2], baseline_indices[index + 1]))
    assert converted_indices == expected_indices


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
def test_mesh_compilation_defaults_front_to_positive_z(tmp_path: Path, space_key: str) -> None:
    compiler = WBEUtilsModelCompiler()
    baseline_output_dir = tmp_path / "baseline"
    converted_output_dir = tmp_path / space_key
    baseline = compiler.compile_mesh(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, baseline_output_dir)
    resource = {**_cube_resource(), space_key: {"front": "-z"}}
    converted = compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, converted_output_dir)

    baseline_submesh = baseline["submeshes"][0]
    converted_submesh = converted["submeshes"][0]
    baseline_path = baseline_output_dir / baseline_submesh["geometry_path"]
    converted_path = converted_output_dir / converted_submesh["geometry_path"]
    baseline_positions = _vec3_section(baseline_path, baseline_submesh, "position")
    converted_positions = _vec3_section(converted_path, converted_submesh, "position")

    for baseline_position, converted_position in zip(baseline_positions, converted_positions, strict=True):
        assert converted_position == pytest.approx((baseline_position[0], baseline_position[1], -baseline_position[2]))


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
@pytest.mark.parametrize("direction", ["X", "forward", "++x", ""])
def test_mesh_compilation_rejects_invalid_direction(tmp_path: Path, space_key: str, direction: str) -> None:
    compiler = WBEUtilsModelCompiler()
    resource = {**_cube_resource(), space_key: {"up": direction}}

    with pytest.raises(ValueError, match="Model direction must be one of"):
        compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
def test_mesh_compilation_rejects_reused_axis(tmp_path: Path, space_key: str) -> None:
    compiler = WBEUtilsModelCompiler()
    resource = {**_cube_resource(), space_key: {"up": "x", "right": "-x"}}

    with pytest.raises(ValueError, match="must use three different axes"):
        compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)


def test_materials_compile_without_absolute_paths(tmp_path: Path) -> None:
    compiler = WBEUtilsModelCompiler()
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
    assert "albedo" in texture_keys
    assert "roughness_metallic_ao" in texture_keys
    for texture_binding in material["textures"]:
        texture = texture_binding["texture"]
        assert texture["type"] == "image"
        assert not Path(texture["file"]).is_absolute()
        assert "path" in texture
        assert not Path(texture["path"]).is_absolute()
        assert texture["color_space"] in {"srgb", "rgb"}
        assert texture["channel_count"] in {3, 4}
