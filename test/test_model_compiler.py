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
from wbe_utils_model_compiler import TextureCompileRequest, WBEUtilsModelCompiler
from wbe_utils_model_compiler import _native


ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_MODEL_DIR = ROOT_DIR / "test-model"


class RecordingTextureCompiler:
    def __init__(self) -> None:
        self.requests: list[TextureCompileRequest] = []

    def compile_texture(self, p_request: TextureCompileRequest) -> None:
        self.requests.append(p_request)
        p_request.destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p_request.source_path, p_request.destination_path)


def _compiler() -> WBEUtilsModelCompiler:
    return WBEUtilsModelCompiler(RecordingTextureCompiler())


def _cube_resource() -> dict[str, object]:
    return {
        "id": "cube",
        "type": "model",
        "file": "Cube/glTF/Cube.gltf",
        "combine_nodes": True,
        "graphics_pipeline_ids": ["main_pipeline"],
        "texture_output_dir": "textures",
        "texture_config": {"target_format": "sbc7", "generate_mipmap": True},
    }


def _make_masked_cube(tmp_path: Path) -> Path:
    source_dir = tmp_path / "Cube"
    shutil.copytree(TEST_MODEL_DIR / "Cube", source_dir)
    source_path = source_dir / "glTF" / "Cube.gltf"
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["materials"][0]["alphaMode"] = "MASK"
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    return source_path


def _make_blend_cube(tmp_path: Path) -> Path:
    source_path = _make_masked_cube(tmp_path)
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["materials"][0]["alphaMode"] = "BLEND"
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    return source_path


def _make_hierarchical_cube(tmp_path: Path) -> Path:
    source_dir = tmp_path / "Cube"
    shutil.copytree(TEST_MODEL_DIR / "Cube", source_dir)
    source_path = source_dir / "glTF" / "Cube.gltf"
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["nodes"] = [
        {
            "children": [1],
            "name": "Parent",
            "scale": [-2.0, 2.0, 2.0],
            "translation": [1.0, 0.0, 0.0],
        },
        {
            "mesh": 0,
            "name": "Child",
            "rotation": [0.0, 0.0, 0.7071067811865475, 0.7071067811865476],
            "translation": [0.0, 3.0, 0.0],
        },
        {
            "mesh": 0,
            "name": "Instance",
            "translation": [0.0, 0.0, 4.0],
        },
    ]
    source_data["scenes"] = [{"nodes": [0, 2]}]
    source_data["scene"] = 0
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    return source_path


def _binary_path(output_dir: Path, submesh: dict[str, object]) -> Path:
    vertices = submesh["vertices"]
    assert isinstance(vertices, dict)
    binary = vertices["binary"]
    assert isinstance(binary, dict)
    binary_id = binary["binary_id"]
    assert isinstance(binary_id, str)
    return output_dir / f"{binary_id}.bin"


def _section_data(geometry_path: Path, submesh: dict[str, object], slot: str) -> bytes:
    if slot == "index":
        indices = submesh["indices"]
        assert isinstance(indices, dict)
        binary_view = indices["binary"]
    else:
        vertices = submesh["vertices"]
        assert isinstance(vertices, dict)
        binary_view = vertices["binary"]
        attributes = vertices["attributes"]
        assert isinstance(attributes, list)
        attribute = next(attribute for attribute in attributes if attribute["role"] == slot)
        stride = vertices["stride"]
        assert isinstance(stride, int)
        data = geometry_path.read_bytes()
        start = binary_view["start"]
        size = binary_view["size"]
        offset = attribute["offset"]
        attribute_type = attribute["type"]
        component_count = 2 if attribute_type == "vec2" else 3
        component_size = component_count * 4
        result = bytearray()
        for vertex_start in range(start, start + size, stride):
            result.extend(data[vertex_start + offset:vertex_start + offset + component_size])
        return bytes(result)
    data = geometry_path.read_bytes()
    start = binary_view["start"]
    size = binary_view["size"]
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


def _material_resources(p_resources: list[dict[str, object]]) -> list[dict[str, object]]:
    return [resource for resource in p_resources if resource.get("type") == "material"]


def _texture_resources(p_resources: list[dict[str, object]]) -> list[dict[str, object]]:
    return [resource for resource in p_resources if resource.get("type") == "texture"]


def _rma_texture_path(
    p_material: dict[str, object], p_resources: list[dict[str, object]], p_output_dir: Path
) -> Path:
    textures = p_material["textures"]
    assert isinstance(textures, list)
    binding = next(texture for texture in textures if texture["texture_role"] == "rma")
    texture_id = binding["texture_id"]
    texture = next(resource for resource in p_resources if resource.get("id") == texture_id)
    return p_output_dir / texture["path"]


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
    compiler = _compiler()
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
    assert "geometry_path" not in submesh
    assert "geometry_sections" not in submesh
    geometry_path = _binary_path(tmp_path, submesh)
    assert geometry_path.is_file()

    vertices = submesh["vertices"]
    indices = submesh["indices"]
    assert isinstance(vertices, dict)
    assert isinstance(indices, dict)
    attributes = {attribute["role"]: attribute for attribute in vertices["attributes"]}
    assert set(attributes) == {"position", "normal", "tangent", "bitangent", "uv"}
    assert attributes["position"]["type"] == "vec3"
    assert attributes["normal"]["type"] == "vec3"
    assert attributes["tangent"]["type"] == "vec3"
    assert attributes["bitangent"]["type"] == "vec3"
    assert attributes["uv"]["type"] == "vec2"
    assert vertices["binary"]["binary_id"] == "cube.mesh.geometry"
    assert indices["binary"]["binary_id"] == "cube.mesh.geometry"
    file_size = geometry_path.stat().st_size
    for binary_view in (vertices["binary"], indices["binary"]):
        assert isinstance(binary_view["start"], int)
        assert isinstance(binary_view["size"], int)
        assert binary_view["start"] + binary_view["size"] <= file_size
    assert vertices["binary"]["size"] % vertices["stride"] == 0
    assert indices["binary"]["size"] % (3 * 4) == 0


def test_compiler_returns_mesh_before_materials(tmp_path: Path) -> None:
    compiler = _compiler()

    compiled = compiler.compile(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert compiled[0]["type"] == "mesh"
    assert compiled[1]["type"] == "binary"
    assert compiled[1]["id"] == "cube.mesh.geometry"
    assert _texture_resources(compiled[2:])
    assert _material_resources(compiled[2:])
    assert len(_texture_resources(compiled[2:])) + len(_material_resources(compiled[2:])) == len(compiled[2:])


def test_mesh_compilation_scales_positions_and_converts_between_coordinate_spaces(tmp_path: Path) -> None:
    compiler = _compiler()
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
    baseline_path = _binary_path(baseline_output_dir, baseline_submesh)
    converted_path = _binary_path(converted_output_dir, converted_submesh)

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


def test_mesh_compilation_combines_node_instances_in_mesh_space(tmp_path: Path) -> None:
    compiler = _compiler()
    baseline_output_dir = tmp_path / "baseline"
    combined_output_dir = tmp_path / "combined"
    baseline = compiler.compile_mesh(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, baseline_output_dir)
    source_path = _make_hierarchical_cube(tmp_path / "source")
    resource = {**_cube_resource(), "file": source_path.as_posix()}

    combined = compiler.compile_mesh(resource, source_path.parent / "manifest.json", source_path.parent, combined_output_dir)

    assert len(combined["submeshes"]) == 2
    assert combined["submeshes"][0]["id"] == "cube.submesh.Cube"
    assert combined["submeshes"][1]["id"] == "cube.submesh.Cube.1"
    baseline_positions = _vec3_section(
        _binary_path(baseline_output_dir, baseline["submeshes"][0]), baseline["submeshes"][0], "position")
    child_positions = _vec3_section(
        _binary_path(combined_output_dir, combined["submeshes"][0]), combined["submeshes"][0], "position")
    instance_positions = _vec3_section(
        _binary_path(combined_output_dir, combined["submeshes"][1]), combined["submeshes"][1], "position")
    for baseline_position, child_position, instance_position in zip(
            baseline_positions, child_positions, instance_positions, strict=True):
        assert child_position == pytest.approx(
            (1.0 + 2.0 * baseline_position[1], 6.0 + 2.0 * baseline_position[0], 2.0 * baseline_position[2]))
        assert instance_position == pytest.approx(
            (baseline_position[0], baseline_position[1], baseline_position[2] + 4.0))
    for slot in ("normal", "tangent", "bitangent"):
        baseline_vectors = _vec3_section(
            _binary_path(baseline_output_dir, baseline["submeshes"][0]), baseline["submeshes"][0], slot)
        child_vectors = _vec3_section(
            _binary_path(combined_output_dir, combined["submeshes"][0]), combined["submeshes"][0], slot)
        instance_vectors = _vec3_section(
            _binary_path(combined_output_dir, combined["submeshes"][1]), combined["submeshes"][1], slot)
        for baseline_vector, child_vector, instance_vector in zip(
                baseline_vectors, child_vectors, instance_vectors, strict=True):
            assert child_vector == pytest.approx((baseline_vector[1], baseline_vector[0], baseline_vector[2]), abs=1.0E-6)
            assert instance_vector == pytest.approx(baseline_vector)
    baseline_indices = _index_section(
        _binary_path(baseline_output_dir, baseline["submeshes"][0]), baseline["submeshes"][0])
    child_indices = _index_section(
        _binary_path(combined_output_dir, combined["submeshes"][0]), combined["submeshes"][0])
    expected_child_indices: list[int] = []
    for index in range(0, len(baseline_indices), 3):
        expected_child_indices.extend((baseline_indices[index], baseline_indices[index + 2], baseline_indices[index + 1]))
    assert child_indices == expected_child_indices


def test_mesh_compilation_reverses_winding_for_negative_position_scale(tmp_path: Path) -> None:
    compiler = _compiler()
    baseline_output_dir = tmp_path / "baseline"
    scaled_output_dir = tmp_path / "scaled"
    baseline = compiler.compile_mesh(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, baseline_output_dir)
    resource = {**_cube_resource(), "scale_vertex_pos": -1.0}

    scaled = compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, scaled_output_dir)

    baseline_submesh = baseline["submeshes"][0]
    scaled_submesh = scaled["submeshes"][0]
    for slot in ("normal", "tangent", "bitangent"):
        baseline_vectors = _vec3_section(_binary_path(baseline_output_dir, baseline_submesh), baseline_submesh, slot)
        scaled_vectors = _vec3_section(_binary_path(scaled_output_dir, scaled_submesh), scaled_submesh, slot)
        for baseline_vector, scaled_vector in zip(baseline_vectors, scaled_vectors, strict=True):
            assert scaled_vector == pytest.approx(tuple(-component for component in baseline_vector))
    baseline_indices = _index_section(_binary_path(baseline_output_dir, baseline_submesh), baseline_submesh)
    scaled_indices = _index_section(_binary_path(scaled_output_dir, scaled_submesh), scaled_submesh)
    expected_indices: list[int] = []
    for index in range(0, len(baseline_indices), 3):
        expected_indices.extend((baseline_indices[index], baseline_indices[index + 2], baseline_indices[index + 1]))
    assert scaled_indices == expected_indices


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
def test_mesh_compilation_defaults_front_to_positive_z(tmp_path: Path, space_key: str) -> None:
    compiler = _compiler()
    baseline_output_dir = tmp_path / "baseline"
    converted_output_dir = tmp_path / space_key
    baseline = compiler.compile_mesh(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, baseline_output_dir)
    resource = {**_cube_resource(), space_key: {"front": "-z"}}
    converted = compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, converted_output_dir)

    baseline_submesh = baseline["submeshes"][0]
    converted_submesh = converted["submeshes"][0]
    baseline_path = _binary_path(baseline_output_dir, baseline_submesh)
    converted_path = _binary_path(converted_output_dir, converted_submesh)
    baseline_positions = _vec3_section(baseline_path, baseline_submesh, "position")
    converted_positions = _vec3_section(converted_path, converted_submesh, "position")

    for baseline_position, converted_position in zip(baseline_positions, converted_positions, strict=True):
        assert converted_position == pytest.approx((baseline_position[0], baseline_position[1], -baseline_position[2]))


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
@pytest.mark.parametrize("direction", ["X", "forward", "++x", ""])
def test_mesh_compilation_rejects_invalid_direction(tmp_path: Path, space_key: str, direction: str) -> None:
    compiler = _compiler()
    resource = {**_cube_resource(), space_key: {"up": direction}}

    with pytest.raises(ValueError, match="Model direction must be one of"):
        compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)


@pytest.mark.parametrize("space_key", ["source_space", "target_space"])
def test_mesh_compilation_rejects_reused_axis(tmp_path: Path, space_key: str) -> None:
    compiler = _compiler()
    resource = {**_cube_resource(), space_key: {"up": "x", "right": "-x"}}

    with pytest.raises(ValueError, match="must use three different axes"):
        compiler.compile_mesh(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)


def test_materials_compile_without_absolute_paths(tmp_path: Path) -> None:
    compiler = _compiler()
    resource = {**_cube_resource(), "masked_graphics_pipeline_ids": ["masked_pipeline"]}
    resources = compiler.compile_materials(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)
    materials = _material_resources(resources)

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
        assert "texture" not in texture_binding
        assert isinstance(texture_binding["texture_id"], str)
    assert len(_texture_resources(resources)) == len(material["textures"])
    assert all(not Path(texture["path"]).is_absolute() for texture in _texture_resources(resources))


def test_materials_reject_duplicate_texture_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    texture_path = output_dir / "duplicate.png"
    texture_path.touch()

    def compile_duplicate_materials(*p_args: object) -> list[dict[str, object]]:
        del p_args
        texture = {"file": texture_path.as_posix(), "source_format": "srgb", "channel_count": 4}
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
    compiler = _compiler()

    with pytest.raises(RuntimeError, match="duplicate material texture role 'albedo'"):
        compiler.compile_materials(_cube_resource(), TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, output_dir)


def test_gltf_material_uses_packed_channels_and_occlusion_red_channel(tmp_path: Path) -> None:
    source_path = _make_masked_cube(tmp_path)
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["materials"][0]["occlusionTexture"] = {"index": 1}
    source_path.write_text(json.dumps(source_data), encoding="utf-8")
    compiler = _compiler()
    output_dir = tmp_path / "output"
    resource = {**_cube_resource(), "file": "Cube/glTF/Cube.gltf"}

    resources = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, output_dir)
    materials = _material_resources(resources)

    width, height, pixels = _read_rgb_png(_rma_texture_path(materials[0], resources, output_dir))
    assert (width, height) == (512, 512)
    assert set(pixels) == {(20, 0, 0)}


def test_standalone_material_maps_use_red_channels(tmp_path: Path) -> None:
    source_path = _write_standalone_pbr_obj(tmp_path / "model")
    compiler = _compiler()
    output_dir = tmp_path / "output"
    resource = {
        "id": "standalone",
        "type": "model",
        "file": source_path.as_posix(),
        "graphics_pipeline_ids": ["main_pipeline"],
        "texture_output_dir": "textures",
        "texture_config": {"target_format": "sbc7", "generate_mipmap": True},
    }

    resources = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, output_dir)
    materials = _material_resources(resources)
    material = next(material for material in materials if material["textures"])

    width, height, pixels = _read_rgb_png(_rma_texture_path(material, resources, output_dir))
    assert (width, height) == (1, 1)
    assert pixels == [(51, 204, 255)]


def test_masked_material_uses_masked_graphics_pipeline(tmp_path: Path) -> None:
    _make_masked_cube(tmp_path)
    compiler = _compiler()
    resource = {**_cube_resource(), "masked_graphics_pipeline_ids": ["masked_pipeline"]}

    resources = compiler.compile_materials(resource, tmp_path / "manifest.json", tmp_path, tmp_path / "output")
    materials = _material_resources(resources)

    assert materials[0]["graphics_pipeline_ids"] == ["masked_pipeline"]


def test_masked_material_falls_back_to_graphics_pipeline(tmp_path: Path) -> None:
    _make_masked_cube(tmp_path)
    compiler = _compiler()

    resources = compiler.compile_materials(_cube_resource(), tmp_path / "manifest.json", tmp_path, tmp_path / "output")
    materials = _material_resources(resources)

    assert materials[0]["graphics_pipeline_ids"] == ["main_pipeline"]


def test_static_geometry_compilation_emits_binary_and_empty_masked_set(tmp_path: Path) -> None:
    compiler = _compiler()
    resource = {**_cube_resource(), "source_type": "static_geometry", "combine_nodes": False}

    compiled = compiler.compile(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)

    assert compiled[0] == {"id": "cube.geometry", "type": "binary", "path": "cube.geometry.bin"}
    assert (tmp_path / "cube.geometry.bin").is_file()
    opaque_set = compiled[1]
    masked_set = compiled[2]
    assert opaque_set["id"] == "cube.static_opaque_set"
    assert opaque_set["type"] == "static_opaque_set"
    assert masked_set["id"] == "cube.static_masked_set"
    assert masked_set["type"] == "static_masked_set"
    assert masked_set["submeshes"] == []
    assert masked_set["instances"] == []
    assert opaque_set["submeshes"]
    assert opaque_set["instances"]
    submesh = opaque_set["submeshes"][0]
    assert submesh["material_id"] == "cube.material.Cube"
    assert submesh["vertices"]["binary"]["binary_id"] == "cube.geometry"
    assert submesh["indices"]["binary"]["binary_id"] == "cube.geometry"
    assert submesh["first_instance"] == 0
    assert submesh["instance_count"] == len(opaque_set["instances"])
    assert len(opaque_set["instances"][0]["global_transform"]) == 16
    assert _texture_resources(compiled[3:])
    assert _material_resources(compiled[3:])
    assert len(_texture_resources(compiled[3:])) + len(_material_resources(compiled[3:])) == len(compiled[3:])


def test_static_geometry_compilation_partitions_masked_materials(tmp_path: Path) -> None:
    _make_masked_cube(tmp_path)
    compiler = _compiler()
    resource = {**_cube_resource(), "source_type": "static_geometry", "combine_nodes": False}

    compiled = compiler.compile(resource, tmp_path / "manifest.json", tmp_path, tmp_path / "output")

    opaque_set = compiled[1]
    masked_set = compiled[2]
    assert opaque_set["submeshes"] == []
    assert opaque_set["instances"] == []
    assert masked_set["submeshes"]
    assert masked_set["instances"]
    assert masked_set["submeshes"][0]["instance_count"] == len(masked_set["instances"])


def test_static_geometry_compilation_omits_blend_materials(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_blend_cube(tmp_path)
    compiler = _compiler()
    resource = {**_cube_resource(), "source_type": "static_geometry", "combine_nodes": False}

    compiled = compiler.compile(resource, tmp_path / "manifest.json", tmp_path, tmp_path / "output")

    captured = capsys.readouterr()
    assert captured.out.count("static_geometry omits BLEND primitives") == 1
    opaque_set = compiled[1]
    masked_set = compiled[2]
    assert opaque_set["submeshes"] == []
    assert opaque_set["instances"] == []
    assert masked_set["submeshes"] == []
    assert masked_set["instances"] == []


def test_static_geometry_compilation_preserves_node_instances(tmp_path: Path) -> None:
    source_path = _make_hierarchical_cube(tmp_path / "source")
    compiler = _compiler()
    resource = {**_cube_resource(), "source_type": "static_geometry", "combine_nodes": False, "file": source_path.as_posix()}

    compiled = compiler.compile_static_geometry(resource, source_path.parent / "manifest.json", source_path.parent, tmp_path / "output")

    opaque_set = compiled[1]
    assert len(opaque_set["submeshes"]) == 1
    assert len(opaque_set["instances"]) == 2
    submesh = opaque_set["submeshes"][0]
    assert submesh["first_instance"] == 0
    assert submesh["instance_count"] == 2
    second_transform = opaque_set["instances"][1]["global_transform"]
    assert second_transform[12:15] == pytest.approx([0.0, 0.0, 4.0])


def test_static_geometry_rejects_combine_nodes(tmp_path: Path) -> None:
    compiler = _compiler()
    resource = {**_cube_resource(), "source_type": "static_geometry"}

    with pytest.raises(ValueError, match="does not support combine_nodes"):
        compiler.compile_static_geometry(resource, TEST_MODEL_DIR / "manifest.json", TEST_MODEL_DIR, tmp_path)


def _prepare_cached_cube_source(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    cache_dir = tmp_path / "cache"
    source_root = tmp_path / "source"
    shutil.copytree(TEST_MODEL_DIR / "Cube", source_root / "Cube")
    resource = {**_cube_resource(), "file": "Cube/glTF/Cube.gltf"}
    return cache_dir, source_root, resource


def _install_compile_counters(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    compile_counts = {"mesh": 0, "static_geometry": 0, "materials": 0}
    original_compile_mesh = _native.compile_mesh
    original_compile_static_geometry = _native.compile_static_geometry
    original_compile_materials = _native.compile_materials

    def counted_compile_mesh(*args: object, **kwargs: object) -> list[dict[str, object]]:
        compile_counts["mesh"] += 1
        return original_compile_mesh(*args, **kwargs)

    def counted_compile_static_geometry(*args: object, **kwargs: object) -> list[dict[str, object]]:
        compile_counts["static_geometry"] += 1
        return original_compile_static_geometry(*args, **kwargs)

    def counted_compile_materials(*args: object, **kwargs: object) -> list[dict[str, object]]:
        compile_counts["materials"] += 1
        return original_compile_materials(*args, **kwargs)

    monkeypatch.setattr(_native, "compile_mesh", counted_compile_mesh)
    monkeypatch.setattr(_native, "compile_static_geometry", counted_compile_static_geometry)
    monkeypatch.setattr(_native, "compile_materials", counted_compile_materials)
    return compile_counts


def test_compile_uses_cache_when_inputs_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    compile_counts = _install_compile_counters(monkeypatch)

    first_result = compiler.compile(resource, manifest_path, source_root, tmp_path / "output", cache_dir=cache_dir)
    second_result = compiler.compile(resource, manifest_path, source_root, tmp_path / "output", cache_dir=cache_dir)

    assert compile_counts == {"mesh": 1, "static_geometry": 0, "materials": 1}
    assert second_result == first_result
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1


def test_compile_rebuilds_when_gltf_dependency_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    output_dir = tmp_path / "output"
    compile_counts = _install_compile_counters(monkeypatch)

    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)
    cube_bin_path = source_root / "Cube" / "glTF" / "Cube.bin"
    cube_bin_data = cube_bin_path.read_bytes()
    cube_bin_path.write_bytes(cube_bin_data + b"\0")
    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)

    assert compile_counts == {"mesh": 2, "static_geometry": 0, "materials": 2}


def test_compile_rebuilds_when_source_file_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    output_dir = tmp_path / "output"
    compile_counts = _install_compile_counters(monkeypatch)

    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)
    source_path = source_root / "Cube" / "glTF" / "Cube.gltf"
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    source_data["scene"] = source_data.get("scene", 0)
    source_path.write_text(json.dumps(source_data, indent=2), encoding="utf-8")
    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)

    assert compile_counts == {"mesh": 2, "static_geometry": 0, "materials": 2}


def test_compile_rebuilds_when_resource_declaration_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    output_dir = tmp_path / "output"
    compile_counts = _install_compile_counters(monkeypatch)

    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)
    modified_resource = {**resource, "texture_output_dir": "textures_cached"}
    compiler.compile(modified_resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)

    assert compile_counts == {"mesh": 2, "static_geometry": 0, "materials": 2}


def test_compile_rebuilds_when_generated_output_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    output_dir = tmp_path / "output"
    compile_counts = _install_compile_counters(monkeypatch)

    compiled = compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)
    binary_resource = next(item for item in compiled if item.get("type") == "binary")
    output_path = output_dir / str(binary_resource["path"])
    output_path.unlink()
    compiler.compile(resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)

    assert compile_counts == {"mesh": 2, "static_geometry": 0, "materials": 2}


def test_static_geometry_compile_uses_cache_when_inputs_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = _compiler()
    cache_dir, source_root, resource = _prepare_cached_cube_source(tmp_path)
    manifest_path = source_root / "manifest.json"
    output_dir = tmp_path / "output"
    compile_counts = _install_compile_counters(monkeypatch)
    static_resource = {**resource, "source_type": "static_geometry", "combine_nodes": False}

    first_result = compiler.compile(static_resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)
    second_result = compiler.compile(static_resource, manifest_path, source_root, output_dir, cache_dir=cache_dir)

    assert compile_counts == {"mesh": 0, "static_geometry": 1, "materials": 1}
    assert second_result == first_result
