# White Bird Engine Utils: Mesh Compiler

Implement the mesh compiler for the White Bird Engine project.

The project is a Python resource compiler package with a C++ native backend.

The goal is to provide a Python API that can compile external mesh assets into White Bird Engine runtime resource descriptions.

---

# General Workflow

Before making changes:

1. Inspect the existing repository structure.
2. Read the existing `AGENTS.md` file.
3. Inspect existing build scripts and project conventions.
4. Identify reusable code before adding new implementations.

Before writing code, provide:

- Current project structure summary.
- Files that will be created or modified.
- Required dependencies.
- Build approach.
- Test approach.

After that, implement the changes.

---

# Project Overview

This project consists of:

- A Python package providing the public compiler interface.
- A C++ native backend providing performance-critical asset processing.
- A pybind11 binding layer connecting C++ and Python.

The C++ implementation is an internal implementation detail.

It is not intended to be a standalone SDK.

---

# Project Structure

The final project should follow this structure:

```

.
├── setup.py
├── requirements.txt
├── build.py
├── CMakeLists.txt
│
├── scripts/
│   └── test/
│       └── ...
│
├── include/
│   └── ...
│
├── src/
│   └── ...
│
├── test/
│   └── ...
│
├── dependencies/
│   └── assimp/
│
└── test-model/
└── ...

```

---

# Python Requirements

The root directory must contain:

```

requirements.txt

```

Before installing dependencies, list all required Python dependencies in this file.

Do not install dependencies yourself.

The Python package must be installable with:

```

pip install .

```

---

# C++ Requirements

The native backend should be implemented in C++.

The build system must use CMake.

The C++ code should be organized as:

```

include/
src/
test/

````

Use include guards.

Do not use:

```cpp
#pragma once
````

for public headers.

---

# Python / C++ Boundary

The Python package is the only consumer of the C++ implementation.

Do not design a generic C API.

Do not expose:

* C structs for Python conversion.
* Manual JSON serialization.
* STL containers across ABI boundaries.
* C++ objects directly to Python.

Use `pybind11`.

The C++ extension should directly return Python-compatible objects:

* dict
* list
* str
* int
* float
* None

Example:

```python
{
    "id": "cube",
    "type": "mesh",
    "submeshes": []
}
```

should be returned directly from C++.

---

# Compiler Architecture

The compiler consists of three layers.

## Frontend

Responsible for importing source assets.

Use Assimp for asset loading.

The frontend converts source assets into internal C++ structures.

Example:

```
Mesh file
    |
    v
Assimp scene
    |
    v
Intermediate C++ structures
```

---

## Intermediate Representation

The intermediate representation is internal to C++.

It should not cross the Python boundary.

Example:

```cpp
struct IntermediateVertex
{
    float position[3];
    float uv[2];
    float normal[3];
    int bone_ids[4];
};
```

The exact implementation can vary.

The IR should be simple and independent from Assimp data structures.

---

## Backend

The backend converts intermediate structures into White Bird runtime resource structures.

The backend creates Python objects through pybind11.

Example:

```
Intermediate Mesh
        |
        v
pybind11 conversion
        |
        v
Python dict
```

---

# Assimp Integration

The project contains Assimp source code:

```
../dependencies/assimp/
```

Build Assimp together with this project.

Use:

```cmake
add_subdirectory()
```

Do not require users to install Assimp separately.

The Assimp path must be configurable from the Python build wrapper.

---

# Build System

The project must build with CMake.

A Python build wrapper must exist:

```
build.py
```

The script is copied from another project and may contain irrelevant logic.

Modify it when necessary.

The script must expose APIs instead of only automatically building.

Required operations:

```
python build.py configure
python build.py build
python build.py test
python build.py clean
```

All paths must be resolved relative to `build.py`.

The user's current working directory must not affect build results.

---

# Mesh Resource Format

The compiled mesh must return:

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
                    "position": {
                        "x": float,
                        "y": float,
                        "z": float
                    },

                    "uv": {
                        "u": float,
                        "v": float
                    },

                    "normal": {
                        "x": float,
                        "y": float,
                        "z": float
                    },

                    "bone_id": list[int] | None
                }
            ],

            "indices_data": list[int],

            "material_id": str | None
        }
    ]
}
```

Field names must match exactly.

Do not rename fields.

---

# Material Resource Format

Materials must return:

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
                "channel_count": int
            }
        }
    ]
}
```

---

# PBR Texture Rules

For PBR workflows:

Combine:

* roughness
* metallic
* ambient occlusion

into one texture.

Channel layout:

```
R -> roughness
G -> metallic
B -> ambient occlusion
```

The generated texture should be:

```python
{
    "texture_key": "roughness_metallic_ao"
}
```

---

# Python Compiler Interface

Implement:

```python
class WBEACPCompiler(abc.ABC):

    @abc.abstractmethod
    def get_supported_resource_types(self) -> list[str]:
        pass


    @abc.abstractmethod
    def compile(
        self,
        resource: ManifestResource,
        manifest_path: Path,
        res_dir: Path,
        res_output_dir: Path
    ) -> ManifestResource:
        pass
```

---

`ManifestResource`:

```python
{
    "type": "mesh",
    "path": str,

    "graphics_pipeline_ids": list[str],

    "texture_output_dir": str
}
```

---

# Responsibilities

Python layer:

* Handle manifests.
* Resolve paths.
* Call native extension.
* Return final compiler resource.
* Manage resource output directories.

C++ layer:

* Load assets.
* Compile meshes.
* Compile materials.
* Create Python objects.

Do not duplicate compiler logic in Python.

---

# Testing Requirements

Tests must include:

## Mesh Test

Using:

```
test-model/
```

verify:

* Mesh can be loaded.
* Compilation succeeds.
* Output type is `"mesh"`.
* Submesh data exists.
* Vertex data is valid.
* Index data is valid.
* Material references are preserved.

## Python Test

Verify:

* Python package imports successfully.
* Native extension loads.
* Compiler interface works.
* Returned objects are Python dictionaries.

---

# Definition of Done

The implementation is complete when:

* [ ] `pip install .` succeeds.
* [ ] CMake build succeeds from clean directory.
* [ ] `build.py` works from any directory.
* [ ] Assimp builds through CMake.
* [ ] Native extension imports from Python.
* [ ] Mesh compiler returns Python dictionaries.
* [ ] Test model compiles successfully.
* [ ] Automated tests pass.
* [ ] No absolute paths are embedded in generated resources.

```
