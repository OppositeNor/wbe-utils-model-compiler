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
from typing import Any

from . import _native


ManifestResource = dict[str, Any]

class WBEUtilsModelCompiler:
    def get_supported_resource_types(self) -> list[str]:
        return ["model"]

    def compile_mesh(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> ManifestResource:
        if resource.get("type") != "model":
            raise ValueError("WBEUtilsModelCompiler only supports model resources.")

        source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        res_output_dir.mkdir(parents=True, exist_ok=True)
        geometry_output_dir, geometry_path_prefix = self._resolve_geometry_output(resource, manifest_path, res_dir, res_output_dir)

        texture_output_dir = str(resource.get("texture_output_dir", ""))
        if texture_output_dir:
            output_path = Path(texture_output_dir)
            resolved_texture_output_dir = output_path if output_path.is_absolute() else res_output_dir / output_path
            resolved_texture_output_dir.mkdir(parents=True, exist_ok=True)

        resource_id = str(resource.get("id", source_path.stem))
        graphics_pipeline_ids = list(resource.get("graphics_pipeline_ids", []))
        vertex_position_scale = float(resource.get("scale_vertex_pos", 1.0))
        source_up, source_right, source_front = self._resolve_coordinate_space(resource, "source_space")
        target_up, target_right, target_front = self._resolve_coordinate_space(resource, "target_space")
        return _native.compile_mesh(
            str(source_path),
            resource_id,
            graphics_pipeline_ids,
            texture_output_dir,
            str(geometry_output_dir),
            geometry_path_prefix,
            vertex_position_scale,
            source_up,
            source_right,
            source_front,
            target_up,
            target_right,
            target_front,
        )

    def compile_materials(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> list[ManifestResource]:
        source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        res_output_dir.mkdir(parents=True, exist_ok=True)
        texture_output_dir = str(resource.get("texture_output_dir", ""))
        resource_id = str(resource.get("id", source_path.stem))
        graphics_pipeline_ids = list(resource.get("graphics_pipeline_ids", []))
        material_resources = _native.compile_materials(str(source_path), resource_id, graphics_pipeline_ids, texture_output_dir)
        self._normalize_material_texture_files(material_resources, source_path, res_dir)
        return material_resources

    def _normalize_material_texture_files(self, material_resources: list[ManifestResource], source_path: Path, res_dir: Path) -> None:
        resource_root = res_dir.resolve()
        source_dir = source_path.parent
        for material_resource in material_resources:
            textures = material_resource.get("textures", [])
            if not isinstance(textures, list):
                continue
            for texture_binding in textures:
                if not isinstance(texture_binding, dict):
                    continue
                texture = texture_binding.get("texture")
                if not isinstance(texture, dict):
                    continue
                raw_file = texture.get("file")
                if not isinstance(raw_file, str) or not raw_file:
                    continue
                texture_file = Path(raw_file)
                resolved_file = texture_file if texture_file.is_absolute() else source_dir / texture_file
                texture["file"] = resolved_file.resolve().relative_to(resource_root).as_posix()

    def _resolve_geometry_output(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> tuple[Path, str]:
        raw_geometry_output_dir = str(resource.get("geometry_output_dir", ""))
        if raw_geometry_output_dir:
            geometry_rel_dir = Path(raw_geometry_output_dir)
            if geometry_rel_dir.is_absolute():
                raise ValueError("geometry_output_dir must be relative to the resource output directory.")
            geometry_rel_dir = Path(geometry_rel_dir.as_posix())
        else:
            try:
                geometry_rel_dir = manifest_path.parent.resolve().relative_to(res_dir.resolve())
            except ValueError:
                geometry_rel_dir = Path("")

        geometry_output_dir = res_output_dir / geometry_rel_dir
        geometry_output_dir.mkdir(parents=True, exist_ok=True)
        geometry_path_prefix = "" if geometry_rel_dir.as_posix() == "." else geometry_rel_dir.as_posix()
        return geometry_output_dir, geometry_path_prefix

    def _resolve_coordinate_space(self, resource: ManifestResource, key: str) -> tuple[str, str, str]:
        space = resource.get(key, {})
        if not isinstance(space, dict):
            raise ValueError(f"{key} must be a dictionary.")
        return str(space.get("up", "y")), str(space.get("right", "x")), str(space.get("front", "z"))

    def _resolve_resource_path(self, resource: ManifestResource, manifest_path: Path, res_dir: Path) -> Path:
        raw_path = Path(str(resource["file"]))
        candidates = [raw_path]
        if not raw_path.is_absolute():
            candidates = [res_dir / raw_path, manifest_path.parent / raw_path]
        for candidate in candidates:
            resolved_candidate = candidate.resolve()
            if resolved_candidate.exists():
                return resolved_candidate
        raise FileNotFoundError(f"Mesh resource path does not exist: {raw_path}")
