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

import hashlib
import json
from pathlib import Path
import shlex
from typing import Any

from . import _native
from ._version import __version__
from .texture_compiler import TextureCompileRequest, TextureCompiler


ManifestResource = dict[str, Any]


class WBEUtilsModelCompiler:
    def __init__(self, texture_compiler: TextureCompiler, cache_dir: Path | None = None) -> None:
        self._texture_compiler = texture_compiler
        self._cache_dir = cache_dir

    def get_supported_resource_types(self) -> list[str]:
        # Advertise the only manifest resource type this compiler can handle.
        return ["model", "static_geometry"]

    def _get_cache_version(self) -> str:
        return f"{__version__}:top-left-uv-v1"

    def compile(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        cache_dir: Path | None = None,
    ) -> list[ManifestResource]:
        active_cache_dir = self._resolve_cache_dir(cache_dir)
        if active_cache_dir is None:
            return self._compile_all_outputs(resource, manifest_path, res_dir, res_output_dir)

        resolved_source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        cache_record_path = self._cache_record_path(
            active_cache_dir, resource, manifest_path, res_dir, res_output_dir, resolved_source_path)
        cached_resources = self._load_cached_resources_if_valid(
            cache_record_path, resource, manifest_path, res_dir, res_output_dir, resolved_source_path)
        if cached_resources is not None:
            return cached_resources

        compiled_resources = self._compile_all_outputs(resource, manifest_path, res_dir, res_output_dir)
        self._write_cache_record(
            cache_record_path, resource, manifest_path, res_dir, res_output_dir, resolved_source_path, compiled_resources)
        return compiled_resources

    def compile_mesh(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        cache_dir: Path | None = None,
    ) -> ManifestResource:
        return self._compile_mesh_resources(resource, manifest_path, res_dir, res_output_dir)[0]

    def _compile_mesh_resources(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> list[ManifestResource]:
        # Reject manifest entries that are routed to the wrong compiler.
        if resource.get("type") != "model":
            raise ValueError("WBEUtilsModelCompiler only supports model resources.")

        # Resolve all output locations before invoking the native compiler.
        source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        res_output_dir.mkdir(parents=True, exist_ok=True)
        geometry_output_dir, geometry_path_prefix = self._resolve_geometry_output(resource, manifest_path, res_dir, res_output_dir)

        texture_output_dir = str(resource.get("texture_output_dir", ""))
        if texture_output_dir:
            # Allow texture extraction into a nested directory under the resource output.
            output_path = Path(texture_output_dir)
            resolved_texture_output_dir = output_path if output_path.is_absolute() else res_output_dir / output_path
            resolved_texture_output_dir.mkdir(parents=True, exist_ok=True)

        # Forward the resolved paths and coordinate space configuration to native code.
        resource_id = str(resource.get("id", source_path.stem))
        graphics_pipeline_ids = list(resource.get("graphics_pipeline_ids", []))
        combine_nodes = bool(resource.get("combine_nodes", False))
        flip_v = resource.get("flip_v", False)
        if not isinstance(flip_v, bool):
            raise ValueError("Model flip_v must be a boolean.")
        vertex_position_scale = float(resource.get("scale_vertex_pos", 1.0))
        source_up, source_right, source_front = self._resolve_coordinate_space(resource, "source_space")
        target_up, target_right, target_front = self._resolve_coordinate_space(resource, "target_space")
        compiled_resources = _native.compile_mesh(
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
            combine_nodes,
            flip_v,
        )
        if not isinstance(compiled_resources, list) or not compiled_resources:
            raise RuntimeError("Model compiler produced no mesh resources.")
        return compiled_resources

    def compile_static_geometry(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        cache_dir: Path | None = None,
    ) -> list[ManifestResource]:
        del cache_dir
        if resource.get("source_type", resource.get("type")) != "static_geometry":
            raise ValueError("WBEUtilsModelCompiler only compiles static geometry from static_geometry resources.")
        if bool(resource.get("combine_nodes", False)):
            raise ValueError("static_geometry preserves nodes as instances and does not support combine_nodes.")

        source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        res_output_dir.mkdir(parents=True, exist_ok=True)
        geometry_output_dir, geometry_path_prefix = self._resolve_geometry_output(resource, manifest_path, res_dir, res_output_dir)
        texture_output_dir = str(resource.get("texture_output_dir", ""))
        resource_id = str(resource.get("id", source_path.stem))
        flip_v = resource.get("flip_v", False)
        if not isinstance(flip_v, bool):
            raise ValueError("Model flip_v must be a boolean.")
        vertex_position_scale = float(resource.get("scale_vertex_pos", 1.0))
        source_up, source_right, source_front = self._resolve_coordinate_space(resource, "source_space")
        target_up, target_right, target_front = self._resolve_coordinate_space(resource, "target_space")
        compiled_resources = _native.compile_static_geometry(
            str(source_path),
            resource_id,
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
            flip_v,
        )
        if not isinstance(compiled_resources, list) or len(compiled_resources) != 4:
            raise RuntimeError("Model compiler produced invalid static geometry resources.")
        return compiled_resources

    def compile_materials(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        cache_dir: Path | None = None,
    ) -> list[ManifestResource]:
        del cache_dir
        # Compile material metadata separately from mesh geometry.
        source_path = self._resolve_resource_path(resource, manifest_path, res_dir)
        res_output_dir.mkdir(parents=True, exist_ok=True)
        texture_output_dir = str(resource.get("texture_output_dir", ""))
        resource_id = str(resource.get("id", source_path.stem))
        graphics_pipeline_ids = list(resource.get("graphics_pipeline_ids", []))
        masked_graphics_pipeline_ids = list(resource.get("masked_graphics_pipeline_ids", []))
        material_resources = _native.compile_materials(
            str(source_path), resource_id, graphics_pipeline_ids, masked_graphics_pipeline_ids, texture_output_dir, str(res_output_dir)
        )
        default_texture_config, role_texture_configs = self._parse_texture_config(resource)
        texture_resources = self._compile_material_textures(
            material_resources,
            source_path,
            res_output_dir,
            resource_id,
            texture_output_dir,
            default_texture_config,
            role_texture_configs,
        )
        return [*texture_resources, *material_resources]

    def _parse_texture_config(
        self, resource: ManifestResource
    ) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
        texture_config = resource.get("texture_config")
        if not isinstance(texture_config, dict):
            raise ValueError("Model resources must declare a texture_config object.")

        default_config = self._parse_texture_role_config(texture_config.get("default"), "texture_config.default")
        roles_value = texture_config.get("roles", {})
        if not isinstance(roles_value, dict):
            raise ValueError("texture_config.roles must be an object.")
        role_configs: dict[str, dict[str, object]] = {}
        for texture_role, role_config in roles_value.items():
            if not isinstance(texture_role, str) or not texture_role:
                raise ValueError("texture_config.roles keys must be non-empty texture roles.")
            role_configs[texture_role] = self._parse_texture_role_config(
                role_config, f"texture_config.roles.{texture_role}")
        return default_config, role_configs

    @staticmethod
    def _parse_texture_role_config(p_config: object, p_config_name: str) -> dict[str, object]:
        if not isinstance(p_config, dict):
            raise ValueError(f"{p_config_name} must be an object.")
        target_format = p_config.get("target_format")
        if target_format not in {"rgb", "srgb", "bc5", "bc7", "sbc7"}:
            raise ValueError(f"{p_config_name}.target_format must be one of rgb, srgb, bc5, bc7, or sbc7.")
        generate_mipmap = p_config.get("generate_mipmap")
        if not isinstance(generate_mipmap, bool):
            raise ValueError(f"{p_config_name}.generate_mipmap must be a boolean.")
        return {"target_format": target_format, "generate_mipmap": generate_mipmap}

    def _compile_material_textures(
        self,
        material_resources: list[ManifestResource],
        source_path: Path,
        res_output_dir: Path,
        resource_id: str,
        texture_output_dir: str,
        default_texture_config: dict[str, object],
        role_texture_configs: dict[str, dict[str, object]],
    ) -> list[ManifestResource]:
        source_dir = source_path.parent
        texture_resources: list[ManifestResource] = []
        compiled_texture_ids: dict[tuple[str, str, str, bool], str] = {}
        for material_resource in material_resources:
            textures = material_resource.get("textures", [])
            if not isinstance(textures, list):
                # Skip malformed material payloads from native code.
                continue
            used_texture_roles: set[str] = set()
            for texture_binding in textures:
                if not isinstance(texture_binding, dict):
                    # Ignore unexpected texture entries instead of crashing normalization.
                    continue
                texture_role = texture_binding.pop("texture_key", None)
                if not isinstance(texture_role, str) or not texture_role:
                    raise RuntimeError("Model compiler produced an empty material texture role.")
                if texture_role in used_texture_roles:
                    raise RuntimeError(f"Model compiler produced duplicate material texture role '{texture_role}'.")
                used_texture_roles.add(texture_role)
                texture_binding["texture_role"] = texture_role
                texture = texture_binding.get("texture")
                if not isinstance(texture, dict):
                    # Only normalize concrete texture resource objects.
                    continue
                raw_file = texture.get("file")
                if not isinstance(raw_file, str) or not raw_file:
                    # Leave non-file-backed textures untouched.
                    continue
                texture_file = Path(raw_file)
                resolved_file = texture_file if texture_file.is_absolute() else source_dir / texture_file
                resolved_file = resolved_file.resolve()
                source_format = texture.get("source_format", texture.get("color_space"))
                if source_format not in {"rgb", "srgb"}:
                    raise RuntimeError("Model compiler produced an unsupported texture source format.")
                texture_config = role_texture_configs.get(texture_role, default_texture_config)
                target_format = str(texture_config["target_format"])
                generate_mipmap = bool(texture_config["generate_mipmap"])
                cache_key = (resolved_file.as_posix(), source_format, target_format, generate_mipmap)
                texture_id = compiled_texture_ids.get(cache_key)
                if texture_id is None:
                    digest = hashlib.sha256("\0".join(map(str, cache_key)).encode("utf-8")).hexdigest()[:16]
                    texture_id = f"{resource_id}.texture.{digest}"
                    source_name = resolved_file.stem
                    output_directory = Path(texture_output_dir) if texture_output_dir else Path("textures")
                    relative_output_path = output_directory / f"{source_name}_{digest}.ktx2"
                    destination_path = (res_output_dir / relative_output_path).resolve()
                    self._texture_compiler.compile_texture(TextureCompileRequest(
                        source_path=resolved_file,
                        destination_path=destination_path,
                        source_format=source_format,
                        target_format=target_format,
                        generate_mipmap=generate_mipmap,
                    ))
                    texture_resources.append({
                        "id": texture_id,
                        "type": "texture",
                        "path": relative_output_path.as_posix(),
                    })
                    compiled_texture_ids[cache_key] = texture_id
                texture_binding.pop("texture", None)
                texture_binding["texture_id"] = texture_id
        return texture_resources

    def _resolve_geometry_output(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> tuple[Path, str]:
        # Respect an explicit geometry output directory when the manifest provides one.
        raw_geometry_output_dir = str(resource.get("geometry_output_dir", ""))
        if raw_geometry_output_dir:
            geometry_rel_dir = Path(raw_geometry_output_dir)
            if geometry_rel_dir.is_absolute():
                # Geometry output stays resource-root-relative so runtime paths remain portable.
                raise ValueError("geometry_output_dir must be relative to the resource output directory.")
            geometry_rel_dir = Path(geometry_rel_dir.as_posix())
        else:
            try:
                # Default to the manifest's directory relative to the resource root.
                geometry_rel_dir = manifest_path.parent.resolve().relative_to(res_dir.resolve())
            except ValueError:
                # Fall back when the manifest does not live under the resource directory.
                geometry_rel_dir = Path("")

        # Return both the concrete output directory and the manifest-facing path prefix.
        geometry_output_dir = res_output_dir / geometry_rel_dir
        geometry_output_dir.mkdir(parents=True, exist_ok=True)
        geometry_path_prefix = "" if geometry_rel_dir.as_posix() == "." else geometry_rel_dir.as_posix()
        return geometry_output_dir, geometry_path_prefix

    def _resolve_coordinate_space(self, resource: ManifestResource, key: str) -> tuple[str, str, str]:
        # Pull a coordinate basis out of the manifest and normalize missing values.
        space = resource.get(key, {})
        if not isinstance(space, dict):
            # Coordinate spaces must be object-shaped so the native layer gets named axes.
            raise ValueError(f"{key} must be a dictionary.")
        return str(space.get("up", "y")), str(space.get("right", "x")), str(space.get("front", "z"))

    def _resolve_resource_path(self, resource: ManifestResource, manifest_path: Path, res_dir: Path) -> Path:
        # Try both resource-root-relative and manifest-relative lookups for source files.
        raw_path = Path(str(resource["file"]))
        candidates = [raw_path]
        if not raw_path.is_absolute():
            # Relative paths may be authored from either common manifest anchor.
            candidates = [res_dir / raw_path, manifest_path.parent / raw_path]
        for candidate in candidates:
            resolved_candidate = candidate.resolve()
            if resolved_candidate.exists():
                # Return the first existing path so downstream native code sees a concrete location.
                return resolved_candidate
        raise FileNotFoundError(f"Mesh resource path does not exist: {raw_path}")

    def _compile_all_outputs(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
    ) -> list[ManifestResource]:
        if resource.get("source_type", resource.get("type")) == "static_geometry":
            static_resources = self.compile_static_geometry(resource, manifest_path, res_dir, res_output_dir)
            material_resources = self.compile_materials({**resource, "type": "model"}, manifest_path, res_dir, res_output_dir)
            return [*static_resources, *material_resources]
        mesh_resources = self._compile_mesh_resources(resource, manifest_path, res_dir, res_output_dir)
        material_resources = self.compile_materials(resource, manifest_path, res_dir, res_output_dir)
        return [*mesh_resources, *material_resources]

    def _resolve_cache_dir(self, cache_dir: Path | None) -> Path | None:
        active_cache_dir = cache_dir if cache_dir is not None else self._cache_dir
        if active_cache_dir is None:
            return None
        return Path(active_cache_dir)

    def _cache_record_path(
        self,
        cache_dir: Path,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        resolved_source_path: Path,
    ) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = {
            "resource_id": str(resource.get("id", resolved_source_path.stem)),
            "resource_type": str(resource.get("source_type", resource.get("type"))),
            "manifest_path": manifest_path.resolve().as_posix(),
            "res_dir": res_dir.resolve().as_posix(),
            "res_output_dir": res_output_dir.resolve().as_posix(),
        }
        digest = hashlib.sha256(json.dumps(cache_key, sort_keys=True).encode("utf-8")).hexdigest()
        return cache_dir / f"{digest}.json"

    def _load_cached_resources_if_valid(
        self,
        cache_record_path: Path,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        resolved_source_path: Path,
    ) -> list[ManifestResource] | None:
        if not cache_record_path.is_file():
            return None
        try:
            cache_record = json.loads(cache_record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(cache_record, dict):
            return None
        if cache_record.get("compiler_version") != self._get_cache_version():
            return None
        if cache_record.get("declaration_hash") != self._build_declaration_hash(
                resource, manifest_path, res_dir, res_output_dir, resolved_source_path):
            return None
        if cache_record.get("source_hash") != self._hash_file(resolved_source_path):
            return None
        dependency_hashes = cache_record.get("dependency_hashes")
        if not isinstance(dependency_hashes, dict):
            return None
        for dependency_path, expected_hash in dependency_hashes.items():
            if not isinstance(dependency_path, str) or not isinstance(expected_hash, str):
                return None
            if self._hash_file(Path(dependency_path)) != expected_hash:
                return None
        compiled_resources = cache_record.get("compiled_resources")
        if not isinstance(compiled_resources, list):
            return None
        if not self._compiled_outputs_exist(compiled_resources, res_output_dir):
            return None
        return compiled_resources

    def _write_cache_record(
        self,
        cache_record_path: Path,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        resolved_source_path: Path,
        compiled_resources: list[ManifestResource],
    ) -> None:
        dependency_paths = self._collect_source_dependencies(resolved_source_path)
        dependency_hashes: dict[str, str] = {}
        for dependency_path in sorted(dependency_paths):
            dependency_hashes[dependency_path.as_posix()] = self._hash_file(dependency_path)
        cache_record = {
            "compiler_version": self._get_cache_version(),
            "declaration_hash": self._build_declaration_hash(resource, manifest_path, res_dir, res_output_dir, resolved_source_path),
            "source_hash": self._hash_file(resolved_source_path),
            "dependency_hashes": dependency_hashes,
            "compiled_resources": compiled_resources,
        }
        cache_record_path.write_text(json.dumps(cache_record, indent=2, sort_keys=True), encoding="utf-8")

    def _build_declaration_hash(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path,
        resolved_source_path: Path,
    ) -> str:
        geometry_output_dir, geometry_path_prefix = self._resolve_geometry_output(resource, manifest_path, res_dir, res_output_dir)
        declaration_payload = {
            "resource": resource,
            "manifest_path": manifest_path.resolve().as_posix(),
            "res_dir": res_dir.resolve().as_posix(),
            "res_output_dir": res_output_dir.resolve().as_posix(),
            "resolved_source_path": resolved_source_path.as_posix(),
            "geometry_output_dir": geometry_output_dir.resolve().as_posix(),
            "geometry_path_prefix": geometry_path_prefix,
        }
        serialized = json.dumps(declaration_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _hash_file(self, path: Path) -> str | None:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError:
            return None
        return digest.hexdigest()

    def _compiled_outputs_exist(self, compiled_resources: list[ManifestResource], res_output_dir: Path) -> bool:
        for output_path in self._collect_output_paths(compiled_resources, res_output_dir):
            if not output_path.is_file():
                return False
        return True

    def _collect_output_paths(self, compiled_resources: list[ManifestResource], res_output_dir: Path) -> set[Path]:
        output_paths: set[Path] = set()
        for resource in compiled_resources:
            if not isinstance(resource, dict):
                continue
            resource_path = resource.get("path")
            if isinstance(resource_path, str) and resource_path:
                output_paths.add(res_output_dir / Path(resource_path))
            textures = resource.get("textures")
            if not isinstance(textures, list):
                continue
            for texture_binding in textures:
                if not isinstance(texture_binding, dict):
                    continue
                texture = texture_binding.get("texture")
                if not isinstance(texture, dict):
                    continue
                texture_path = texture.get("path")
                if isinstance(texture_path, str) and texture_path:
                    output_paths.add(res_output_dir / Path(texture_path))
        return output_paths

    def _collect_source_dependencies(self, source_path: Path) -> set[Path]:
        suffix = source_path.suffix.lower()
        if suffix == ".gltf":
            return self._collect_gltf_dependencies(source_path)
        if suffix == ".obj":
            return self._collect_obj_dependencies(source_path)
        return set()

    def _collect_gltf_dependencies(self, source_path: Path) -> set[Path]:
        try:
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        dependency_paths: set[Path] = set()
        for group_key in ("buffers", "images"):
            group = source_data.get(group_key, [])
            if not isinstance(group, list):
                continue
            for entry in group:
                if not isinstance(entry, dict):
                    continue
                uri = entry.get("uri")
                if not isinstance(uri, str) or not uri or uri.startswith("data:") or "://" in uri:
                    continue
                dependency_paths.add((source_path.parent / uri).resolve())
        return dependency_paths

    def _collect_obj_dependencies(self, source_path: Path) -> set[Path]:
        dependency_paths: set[Path] = set()
        try:
            lines = source_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return dependency_paths
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not stripped.startswith("mtllib "):
                continue
            for mtl_name in stripped.split()[1:]:
                mtl_path = (source_path.parent / mtl_name).resolve()
                dependency_paths.add(mtl_path)
                dependency_paths.update(self._collect_mtl_dependencies(mtl_path))
        return dependency_paths

    def _collect_mtl_dependencies(self, mtl_path: Path) -> set[Path]:
        dependency_paths: set[Path] = set()
        try:
            lines = mtl_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return dependency_paths
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            tokens = shlex.split(stripped, comments=False, posix=True)
            if len(tokens) < 2:
                continue
            command = tokens[0].lower()
            if not (command.startswith("map_") or command in {"bump", "disp", "decal", "refl"}):
                continue
            dependency_paths.add((mtl_path.parent / tokens[-1]).resolve())
        return dependency_paths
