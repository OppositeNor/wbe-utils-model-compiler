# wbe-utils-model-compiler

`wbe-utils-model-compiler` compiles external mesh assets into White Bird Engine runtime resource dictionaries.

The public API is a Python package. Mesh loading and resource conversion are implemented in a C++23 native extension built with CMake, pybind11, and Assimp.

## What It Produces

The compiler returns Python dictionaries that match White Bird Engine resource formats. Model compilation returns a mesh resource with submeshes, binary geometry section descriptors, sidecar geometry binaries, and material references. Material compilation returns material resources with pipeline IDs and texture bindings.

The native layer returns Python-compatible objects directly through pybind11. It does not expose C structs, STL containers, or C++ objects as part of the public Python API.

## Repository Layout

```text
.
├── CMakeLists.txt
├── build.py
├── pyproject.toml
├── setup.py
├── include/
├── src/
├── test/
├── test-model/
└── wbe_utils_model_compiler/
```

Dependencies are expected to exist beside this repository:

```text
..
```

The path can be overridden with `WBE_DEPENDENCIES_ROOT` or `--dependencies-root`.

## Requirements

- Python 3.10 or newer
- CMake 3.22 or newer
- A C++23 compiler
- Python build and test packages listed in `pyproject.toml`
- Assimp source at `../assimp/` or a custom source path

Assimp is built from source with this project by CMake. It is not loaded through `pkg-config` and does not need to be installed system-wide.

## Build Commands

The build wrapper resolves paths relative to `build.py`, so the current working directory does not affect build output.

```sh
python build.py configure
python build.py build
python build.py test
python build.py clean
```

Use a custom dependencies directory when needed:

```sh
python build.py configure --dependencies-root /path/to/dependencies
```

The same path can be supplied with an environment variable:

```sh
WBE_DEPENDENCIES_ROOT=/path/to/dependencies python build.py build
```

## Install

From the repository root:

```sh
pip install .
```

If the environment is already prepared and dependency installation should be skipped:

```sh
pip install . --no-deps --no-build-isolation
```

## Python Usage

```python
from pathlib import Path

from wbe_utils_model_compiler import WBEUtilsModelCompiler


compiler = WBEUtilsModelCompiler()

resource = {
	"id": "cube",
	"type": "model",
	"file": "Cube/glTF/Cube.gltf",
	"graphics_pipeline_ids": ["main_pipeline"],
	"masked_graphics_pipeline_ids": ["masked_pipeline"],
	"texture_output_dir": "textures",
}

mesh_resource = compiler.compile_mesh(
	resource=resource,
	manifest_path=Path("test-model/manifest.json"),
	res_dir=Path("test-model"),
	res_output_dir=Path("build/resources"),
)

material_resources = compiler.compile_materials(
	resource=resource,
	manifest_path=Path("test-model/manifest.json"),
	res_dir=Path("test-model"),
	res_output_dir=Path("build/resources"),
)
```

`res_dir` is used to resolve relative resource paths first. If the resource path is not found there, it is resolved relative to `manifest_path.parent`.
`res_output_dir` is the root for emitted geometry sidecar binaries, copied material textures, and generated texture artifacts.

## Manifest Resource Input

```python
{
	"id": str,
	"type": "model",
	"file": str,
	"graphics_pipeline_ids": list[str],
	"masked_graphics_pipeline_ids": list[str],
	"texture_output_dir": str,
	"geometry_output_dir": str,
	"scale_vertex_pos": float,
	"source_space": {
		"up": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
		"right": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
		"front": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
	},
	"target_space": {
		"up": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
		"right": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
		"front": "x" | "y" | "z" | "-x" | "-y" | "-z" | "+x" | "+y" | "+z",
	},
}
```

Materials tagged with glTF `alphaMode: "MASK"` use `masked_graphics_pipeline_ids`. If that list is absent or empty, they fall back to `graphics_pipeline_ids`.

All fields except `type` and `file` are optional at runtime. When `id` is omitted, the source file stem is used. `geometry_output_dir` is resource-root-relative; when omitted, geometry sidecars are emitted near the declaring manifest path under `res_output_dir`. `scale_vertex_pos` defaults to `1.0`. Both coordinate spaces default to `up: "y"`, `right: "x"`, and `front: "+z"`; omitted directions use the same defaults. Unsigned and `+`-prefixed positive axes are equivalent.

When `texture_output_dir` is provided, regular source textures are copied under `res_output_dir / texture_output_dir`, and generated textures such as repacked roughness-metallic-ambient-occlusion images are emitted there as well.

## Mesh Resource Output

```python
{
	"id": str,
	"type": "mesh",
	"submeshes": [
		{
			"id": str,
			"type": "submesh",
			"geometry_path": str,
			"geometry_sections": [
				{"slot": "position", "start": int, "size": int, "type": "vec3"},
				{"slot": "normal", "start": int, "size": int, "type": "vec3"},
				{"slot": "tangent", "start": int, "size": int, "type": "vec3"},
				{"slot": "bitangent", "start": int, "size": int, "type": "vec3"},
				{"slot": "uv", "start": int, "size": int, "type": "vec2"},
				{"slot": "index", "start": int, "size": int, "type": "uint32"},
			],
			"material_id": str | None,
		}
	],
}
```

Geometry sidecar binaries contain raw little-endian `float32` vertex attribute values and `uint32` indices with no file header. Section metadata is stored only in the JSON resource. The native importer asks Assimp to generate tangent space and emits `tangent` and `bitangent` sections when tangent data is available for the source mesh.

## Material Resource Output

```python
{
	"id": str,
	"type": "material",
	"graphics_pipeline_ids": list[str],
	"textures": [
		{
			"texture_key": str,
			"texture": {
				"type": "image",
				"file": str,
				"color_space": str,
				"channel_count": int,
			},
		}
	],
}
```

For PBR assets, roughness, metallic, and ambient occlusion are represented by one `rma` texture binding. The expected channel layout is:

```text
R -> roughness
G -> metallic
B -> ambient occlusion
```

Generated resource paths are relative; absolute source paths are not embedded in returned texture resources.
For emitted material textures, `texture.file` is relative to `res_output_dir`, typically under `texture_output_dir` when that field is configured.

## Tests

Run the full test path through the build wrapper:

```sh
python build.py test
```

The tests compile `test-model/Cube/glTF/Cube.gltf` and verify package import, native extension loading, mesh output fields, geometry sidecar files and sections, material references, copied/generated texture bindings, and relative texture paths.
