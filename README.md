# wbe-utils-mesh-compiler

`wbe-utils-mesh-compiler` compiles external mesh assets into White Bird Engine runtime resource dictionaries.

The public API is a Python package. Mesh loading and resource conversion are implemented in a C++23 native extension built with CMake, pybind11, and Assimp.

## What It Produces

The compiler returns Python dictionaries that match White Bird Engine resource formats. Mesh compilation returns a mesh resource with submeshes, vertex data, indices, and material references. Material compilation returns material resources with pipeline IDs and texture bindings.

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
└── wbe_utils_mesh_compiler/
```

Assimp is expected to exist beside this repository:

```text
../dependencies/assimp/
```

The path can be overridden with `WBE_ASSIMP_ROOT` or `--assimp-root`.

## Requirements

- Python 3.10 or newer
- CMake 3.22 or newer
- A C++23 compiler
- Python build and test packages listed in `pyproject.toml`
- Assimp source at `../dependencies/assimp/` or a custom source path

Assimp is built from source with this project by CMake. It is not loaded through `pkg-config` and does not need to be installed system-wide.

## Build Commands

The build wrapper resolves paths relative to `build.py`, so the current working directory does not affect build output.

```sh
python build.py configure
python build.py build
python build.py test
python build.py clean
```

Use a custom Assimp source path when needed:

```sh
python build.py configure --assimp-root /path/to/assimp
```

The same path can be supplied with an environment variable:

```sh
WBE_ASSIMP_ROOT=/path/to/assimp python build.py build
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

from wbe_utils_mesh_compiler import WBEMeshCompiler


compiler = WBEMeshCompiler()

resource = {
	"id": "cube",
	"type": "mesh",
	"path": "Cube/glTF/Cube.gltf",
	"graphics_pipeline_ids": ["main_pipeline"],
	"texture_output_dir": "textures",
}

mesh_resource = compiler.compile(
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

## Manifest Resource Input

```python
{
	"id": str,
	"type": "mesh",
	"path": str,
	"graphics_pipeline_ids": list[str],
	"texture_output_dir": str,
}
```

`id`, `graphics_pipeline_ids`, and `texture_output_dir` are optional at runtime. When `id` is omitted, the source file stem is used.

## Mesh Resource Output

```python
{
	"id": str,
	"type": "mesh",
	"submeshes": [
		{
			"id": str,
			"type": "submesh",
			"vertices_data": [
				{
					"position": {"x": float, "y": float, "z": float},
					"uv": {"u": float, "v": float},
					"normal": {"x": float, "y": float, "z": float},
					"bones": [{"index": int, "weight": float}] | None,
				}
			],
			"indices_data": list[int],
			"material_id": str | None,
		}
	],
}
```

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
				"path": str,
				"color_space": str,
				"channel_count": int,
			},
		}
	],
}
```

For PBR assets, roughness, metallic, and ambient occlusion are represented by one `roughness_metallic_ao` texture binding. The expected channel layout is:

```text
R -> roughness
G -> metallic
B -> ambient occlusion
```

Generated resource paths are relative; absolute source paths are not embedded in returned texture resources.

## Tests

Run the full test path through the build wrapper:

```sh
python build.py test
```

The tests compile `test-model/Cube/glTF/Cube.gltf` and verify package import, native extension loading, mesh output fields, vertex/index data, material references, texture bindings, and relative texture paths.
