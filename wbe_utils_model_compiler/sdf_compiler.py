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
import math
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable

import numpy as np


ManifestResource = dict[str, Any]

SDF_DATA_STRUCTURES = ("texture_3d",)
_MESH_CATEGORIES = ("opaque_instances", "masked_instances", "double_sided_opaque_instances")
_POSITION_BYTE_SIZE = 12
_TRIANGLE_INDICES_BYTE_SIZE = 12
# Fraction of a sample by which float32 bounds may exceed a whole number of samples without adding one.
_EXTENT_TOLERANCE = 1.0E-3


@dataclass(frozen=True)
class SDFConfig:
    """Enabled `sdf_config` of a mesh declaration; resolution is the number of samples per unit of distance."""

    resolution: float
    data_structure: str

    @staticmethod
    def parse(p_declaration: ManifestResource) -> SDFConfig | None:
        """
        Parse the `sdf_config` of a mesh declaration. Other fields are read only when `enabled` is true.

        :return: The configuration, or None when `sdf_config` is absent or disabled.
        :raises ValueError: If `sdf_config` is malformed.
        """
        sdf_config = p_declaration.get("sdf_config")
        if sdf_config is None:
            return None
        if not isinstance(sdf_config, dict):
            raise ValueError("sdf_config must be an object.")
        enabled = sdf_config.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("sdf_config.enabled must be a boolean.")
        if not enabled:
            return None
        resolution = sdf_config.get("resolution")
        if resolution is None:
            raise ValueError("sdf_config.resolution is required when sdf_config is enabled.")
        if not isinstance(resolution, int | float) or isinstance(resolution, bool):
            raise ValueError("sdf_config.resolution must be a number.")
        if not math.isfinite(resolution):
            raise ValueError("sdf_config.resolution must be finite.")
        if resolution <= 0:
            raise ValueError("sdf_config.resolution must be positive.")
        data_structure = sdf_config.get("data_structure")
        if data_structure is None:
            raise ValueError("sdf_config.data_structure is required when sdf_config is enabled.")
        if data_structure not in SDF_DATA_STRUCTURES:
            raise ValueError(f"sdf_config.data_structure must be one of: {', '.join(SDF_DATA_STRUCTURES)}.")
        return SDFConfig(resolution=float(resolution), data_structure=data_structure)


@dataclass(frozen=True)
class SDFCompileRequest:
    """
    Uniform sampling of the signed distance to one triangle mesh.

    vertex_positions is an (N, 3) float32 array and triangle_indices an (M, 3) uint32 array of indices into it. The samples
    form an extent[0] x extent[1] x extent[2] grid, and sample (x, y, z) lies at sample_origin + (x, y, z) * sample_spacing,
    in the space of vertex_positions. destination_path ends with `.ktx2`.
    """

    vertex_positions: np.ndarray
    triangle_indices: np.ndarray
    sample_origin: tuple[float, float, float]
    sample_spacing: float
    extent: tuple[int, int, int]
    data_structure: str
    destination_path: Path


@runtime_checkable
class SDFCompiler(Protocol):
    """Interface implemented by the host asset-conditioning pipeline."""

    def compile_sdf(self, p_request: SDFCompileRequest) -> None:
        """
        Write the signed distance at every sample to destination_path, negative inside the mesh.

        A texture_3d request is written as a 3D KTX2 texture of extent texels with one mip level, no supercompression, and the
        VK_FORMAT_R16_SFLOAT format; texel (x, y, z) holds sample (x, y, z). Each stored distance is rounded toward zero, so
        its magnitude never exceeds the sampled one.
        """


class MeshSDFBuilder:
    """
    Emit the signed distance field of a compiled mesh, sampled by an SDFCompiler.

    The triangles are read back from the binaries the mesh was compiled into and placed by every instance that draws them, so
    the field is in mesh space. The samples cover the bounds of those triangles, enlarged to a whole number of samples per
    axis about their center, with each sample at the center of its cell.
    """

    def __init__(self, p_sdf_compiler: SDFCompiler | None) -> None:
        """
        :param p_sdf_compiler: The compiler that samples the fields, or None when no declaration enables one.
        """
        self._sdf_compiler = p_sdf_compiler

    def build(
        self,
        p_mesh: ManifestResource,
        p_resources: list[ManifestResource],
        p_config: SDFConfig,
        p_res_output_dir: Path,
        p_output_dir: Path,
    ) -> list[ManifestResource]:
        """
        Sample the field of a compiled mesh and reference it from the mesh's `sdf_id`.

        :param p_mesh: The compiled mesh resource, which receives `sdf_id`.
        :param p_resources: The compiled resources, holding every binary the mesh's submeshes reference.
        :param p_res_output_dir: The resource output root that binary paths are relative to.
        :param p_output_dir: The resource-root-relative directory of the emitted SDF texture.
        :return: The SDF `texture` resource followed by the `sdf` resource.
        :raises RuntimeError: If no SDF compiler was provided, the mesh has no id or draws no triangle, a submesh geometry
            view is invalid or references a binary missing from p_resources, or the compiler wrote no texture.
        """
        if self._sdf_compiler is None:
            raise RuntimeError("sdf_config is enabled, but no SDF compiler was provided.")
        mesh_id = p_mesh.get("id")
        if not isinstance(mesh_id, str) or not mesh_id:
            raise RuntimeError("Cannot compile the SDF of a mesh without an id.")
        binary_paths = {
            resource["id"]: p_res_output_dir / Path(resource["path"])
            for resource in p_resources
            if resource.get("type") == "binary"
        }
        vertex_positions, triangle_indices = self._collect_triangles(mesh_id, p_mesh, binary_paths)

        triangle_vertices = vertex_positions[triangle_indices.reshape(-1)].astype(np.float64)
        minimum = triangle_vertices.min(axis=0)
        maximum = triangle_vertices.max(axis=0)
        center = (minimum + maximum) * 0.5
        spacing = 1.0 / p_config.resolution
        extent = tuple(max(1, math.ceil(float(size) * p_config.resolution - _EXTENT_TOLERANCE)) for size in maximum - minimum)
        covered_size = np.array(extent, dtype=np.float64) * spacing
        sample_origin = center - (covered_size * 0.5) + (spacing * 0.5)

        sdf_id = f"{mesh_id}.sdf"
        texture_id = f"{mesh_id}.sdf_texture"
        relative_path = p_output_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', texture_id)}.ktx2"
        destination_path = p_res_output_dir / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        # A texture from an earlier build must not pass for the compiler's output.
        destination_path.unlink(missing_ok=True)
        self._sdf_compiler.compile_sdf(SDFCompileRequest(
            vertex_positions=vertex_positions,
            triangle_indices=triangle_indices,
            sample_origin=(float(sample_origin[0]), float(sample_origin[1]), float(sample_origin[2])),
            sample_spacing=spacing,
            extent=(extent[0], extent[1], extent[2]),
            data_structure=p_config.data_structure,
            destination_path=destination_path,
        ))
        if not destination_path.is_file():
            raise RuntimeError(f"The SDF compiler did not write the texture of mesh '{mesh_id}' to {destination_path}.")

        p_mesh["sdf_id"] = sdf_id
        return [
            {"id": texture_id, "type": "texture", "path": relative_path.as_posix()},
            {
                "id": sdf_id,
                "type": "sdf",
                "data_structure": p_config.data_structure,
                "texture_id": texture_id,
                "aabb": {
                    "center": [float(component) for component in center],
                    "width": float(covered_size[0]),
                    "height": float(covered_size[1]),
                    "depth": float(covered_size[2]),
                },
            },
        ]

    def _collect_triangles(
        self, p_mesh_id: str, p_mesh: ManifestResource, p_binary_paths: dict[str, Path]
    ) -> tuple[np.ndarray, np.ndarray]:
        binaries: dict[str, np.ndarray] = {}
        vertex_positions: list[np.ndarray] = []
        triangle_indices: list[np.ndarray] = []
        vertex_count = 0
        for category_name in _MESH_CATEGORIES:
            category = p_mesh[category_name]
            instances = category["instances"]
            for submesh in category["submeshes"]:
                positions = self._read_positions(p_mesh_id, submesh, p_binary_paths, binaries)
                indices = self._read_indices(p_mesh_id, submesh, len(positions), p_binary_paths, binaries)
                first_instance = submesh["first_instance"]
                for instance in instances[first_instance:first_instance + submesh["instance_count"]]:
                    # Instance transforms are column-major.
                    transform = np.array(instance["global_transform"], dtype=np.float64).reshape(4, 4).T
                    vertex_positions.append(positions @ transform[:3, :3].T + transform[:3, 3])
                    triangle_indices.append(indices + vertex_count)
                    vertex_count += len(positions)
        if sum(len(indices) for indices in triangle_indices) == 0:
            raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': it draws no triangle.")
        return np.concatenate(vertex_positions).astype(np.float32), np.concatenate(triangle_indices).astype(np.uint32)

    def _read_positions(
        self,
        p_mesh_id: str,
        p_submesh: ManifestResource,
        p_binary_paths: dict[str, Path],
        p_binaries: dict[str, np.ndarray],
    ) -> np.ndarray:
        for vertex_binding in p_submesh["vertex_bindings"]:
            for attribute in vertex_binding["attributes"]:
                if attribute["role"] != "position":
                    continue
                if attribute["type"] != "vec3":
                    raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh position is not a vec3.")
                stride = vertex_binding["stride"]
                offset = attribute["offset"]
                if offset + _POSITION_BYTE_SIZE > stride:
                    raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh position exceeds its vertex stride.")
                vertex_bytes = self._read_view(p_mesh_id, vertex_binding["binary"], p_binary_paths, p_binaries)
                if len(vertex_bytes) % stride != 0:
                    raise RuntimeError(
                        f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh vertex view is not a multiple of its stride.")
                positions = vertex_bytes.reshape(-1, stride)[:, offset:offset + _POSITION_BYTE_SIZE]
                return np.ascontiguousarray(positions).view("<f4").astype(np.float64)
        raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh declares no position attribute.")

    def _read_indices(
        self,
        p_mesh_id: str,
        p_submesh: ManifestResource,
        p_vertex_count: int,
        p_binary_paths: dict[str, Path],
        p_binaries: dict[str, np.ndarray],
    ) -> np.ndarray:
        index_bytes = self._read_view(p_mesh_id, p_submesh["indices"]["binary"], p_binary_paths, p_binaries)
        if len(index_bytes) % _TRIANGLE_INDICES_BYTE_SIZE != 0:
            raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh index view holds partial triangles.")
        indices = index_bytes.view("<u4").reshape(-1, 3).astype(np.int64)
        if indices.size > 0 and int(indices.max()) >= p_vertex_count:
            raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a submesh index is out of range.")
        return indices

    def _read_view(
        self,
        p_mesh_id: str,
        p_view: ManifestResource,
        p_binary_paths: dict[str, Path],
        p_binaries: dict[str, np.ndarray],
    ) -> np.ndarray:
        binary_id = p_view["binary_id"]
        binary = p_binaries.get(binary_id)
        if binary is None:
            binary_path = p_binary_paths.get(binary_id)
            if binary_path is None:
                raise RuntimeError(
                    f"Cannot compile the SDF of mesh '{p_mesh_id}': its binary '{binary_id}' is not compiled with the mesh.")
            binary = np.fromfile(binary_path, dtype=np.uint8)
            p_binaries[binary_id] = binary
        start = p_view["start"]
        size = p_view["size"]
        if start + size > len(binary):
            raise RuntimeError(f"Cannot compile the SDF of mesh '{p_mesh_id}': a view exceeds binary '{binary_id}'.")
        return binary[start:start + size]
