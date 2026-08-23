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

import json
from pathlib import Path
import shutil
import struct
import zlib

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


def _make_masked_cube(tmp_path: Path) -> Path:
    source_dir = tmp_path / "Cube"
    shutil.copytree(TEST_MODEL_DIR / "Cube", source_dir)
    source_path = source_dir / "glTF" / "Cube.gltf"
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["materials"][0]["alphaMode"] = "MASK"
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    return source_path


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


def _paeth_predictor(p_left: int, p_up: int, p_upper_left: int) -> int:
    estimate = p_left + p_up - p_upper_left
    left_distance = abs(estimate - p_left)
    up_distance = abs(estimate - p_up)
    upper_left_distance = abs(estimate - p_upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return p_left
    if up_distance <= upper_left_distance:
        return p_up
    return p_upper_left


def _read_rgb_png(p_path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = p_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    width = 0
    height = 0
    compressed_data = bytearray()
    while offset < len(data):
        chunk_size = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + chunk_size]
        offset += 12 + chunk_size
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk_data)
            assert (bit_depth, color_type, compression, filtering, interlace) == (8, 2, 0, 0, 0)
        elif chunk_type == b"IDAT":
            compressed_data.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    row_size = width * 3
    filtered_data = zlib.decompress(compressed_data)
    previous_row = bytearray(row_size)
    pixels: list[tuple[int, int, int]] = []
    data_offset = 0
    for _ in range(height):
        filter_type = filtered_data[data_offset]
        data_offset += 1
        filtered_row = filtered_data[data_offset:data_offset + row_size]
        data_offset += row_size
        row = bytearray(row_size)
        for index, value in enumerate(filtered_row):
            left = row[index - 3] if index >= 3 else 0
            up = previous_row[index]
            upper_left = previous_row[index - 3] if index >= 3 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                assert filter_type == 4
                predictor = _paeth_predictor(left, up, upper_left)
            row[index] = (value + predictor) & 0xFF
        pixels.extend(tuple(row[index:index + 3]) for index in range(0, row_size, 3))
        previous_row = row
    return width, height, pixels


def _rma_texture_path(p_material: dict[str, object], p_output_dir: Path) -> Path:
    textures = p_material["textures"]
    assert isinstance(textures, list)
    binding = next(texture for texture in textures if texture["texture_role"] == "rma")
    return p_output_dir / binding["texture"]["path"]


def _write_standalone_pbr_obj(p_directory: Path) -> Path:
    p_directory.mkdir(parents=True)
    (p_directory / "metallic.ppm").write_bytes(b"P6\n1 1\n255\n" + bytes((204, 17, 34)))
    (p_directory / "roughness.ppm").write_bytes(b"P6\n1 1\n255\n" + bytes((51, 102, 153)))
    (p_directory / "material.mtl").write_text(
        "newmtl material\nKd 1 1 1\nmap_Pm metallic.ppm\nmap_Pr roughness.ppm\n", encoding="utf-8")
    source_path = p_directory / "triangle.obj"
    source_path.write_text(
        "mtllib material.mtl\no triangle\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\n"
        "vn 0 0 1\nusemtl material\nf 1/1/1 2/2/1 3/3/1\n",
        encoding="utf-8",
    )
    return source_path


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


def test_compiler_returns_mesh_before_materials(tmp_path: Path) -> None:
    compiler = WBEUtilsModelCompiler()

    compiled = compiler.compile(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert compiled[0]["type"] == "mesh"
    assert all(resource["type"] == "material" for resource in compiled[1:])


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
    resource = {**_cube_resource(), "masked_graphics_pipeline_ids": ["masked_pipeline"]}
    materials = compiler.compile_materials(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert isinstance(materials, list)
    assert materials
    material = materials[0]
    assert material["id"] == "cube.material.Cube"
    assert material["type"] == "material"
    assert material["graphics_pipeline_ids"] == ["main_pipeline"]
    assert isinstance(material["textures"], list)
    assert material["textures"]

    texture_roles = {texture["texture_role"] for texture in material["textures"]}
    assert "albedo" in texture_roles
    assert "rma" in texture_roles
    for texture_binding in material["textures"]:
        assert "texture_key" not in texture_binding
        texture = texture_binding["texture"]
        assert texture["type"] == "image"
        assert "file" not in texture
        assert not Path(texture["path"]).is_absolute()
        assert texture["flip_v"] is True
        assert texture["color_space"] in {"srgb", "rgb"}
        assert texture["channel_count"] in {3, 4}


def test_materials_reject_duplicate_texture_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    texture_path = output_dir / "duplicate.png"
    texture_path.touch()

    def compile_duplicate_materials(*p_args: object) -> list[dict[str, object]]:
        del p_args
        texture = {"type": "image", "file": texture_path.as_posix(), "color_space": "srgb", "channel_count": 4}
        return [{
            "id": "duplicate.material",
            "type": "material",
            "graphics_pipeline_ids": ["main_pipeline"],
            "textures": [
                {"texture_key": "albedo", "texture": dict(texture)},
                {"texture_key": "albedo", "texture": dict(texture)},
            ],
        }]

    monkeypatch.setattr(_native, "compile_materials", compile_duplicate_materials)
    compiler = WBEUtilsModelCompiler()

    with pytest.raises(RuntimeError, match="duplicate material texture role 'albedo'"):
        compiler.compile_materials(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, output_dir)


def test_gltf_material_uses_packed_channels_and_occlusion_red_channel(tmp_path: Path) -> None:
    source_path = _make_masked_cube(tmp_path)
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["materials"][0]["occlusionTexture"] = {"index": 1}
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    compiler = WBEUtilsModelCompiler()
    output_dir = tmp_path / "output"
    resource = {**_cube_resource(), "file": "Cube/glTF/Cube.gltf"}

    materials = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, output_dir)

    width, height, pixels = _read_rgb_png(_rma_texture_path(materials[0], output_dir))
    assert (width, height) == (512, 512)
    assert set(pixels) == {(20, 0, 0)}


def test_standalone_material_maps_use_red_channels(tmp_path: Path) -> None:
    source_path = _write_standalone_pbr_obj(tmp_path / "model")
    compiler = WBEUtilsModelCompiler()
    output_dir = tmp_path / "output"
    resource = {
        "id": "standalone",
        "type": "model",
        "file": source_path.as_posix(),
        "graphics_pipeline_ids": ["main_pipeline"],
        "texture_output_dir": "textures",
    }

    materials = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, output_dir)
    material = next(material for material in materials if material["textures"])

    width, height, pixels = _read_rgb_png(_rma_texture_path(material, output_dir))
    assert (width, height) == (1, 1)
    assert pixels == [(51, 204, 255)]


def test_masked_material_uses_masked_graphics_pipeline(tmp_path: Path) -> None:
    _make_masked_cube(tmp_path)
    compiler = WBEUtilsModelCompiler()
    resource = {**_cube_resource(), "masked_graphics_pipeline_ids": ["masked_pipeline"]}

    materials = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, tmp_path / "output")

    assert materials[0]["graphics_pipeline_ids"] == ["masked_pipeline"]


def test_masked_material_falls_back_to_graphics_pipeline(tmp_path: Path) -> None:
    _make_masked_cube(tmp_path)
    compiler = WBEUtilsModelCompiler()

    materials = compiler.compile_materials(_cube_resource(), tmp_path / "manifest.json", tmp_path, tmp_path / "output")

    assert materials[0]["graphics_pipeline_ids"] == ["main_pipeline"]
