# White Bird Engine — Conventions

Compact reference for AI agents. High info density, low fluff.

## Change Discipline

- Make the smallest change that solves the problem.
- Do not refactor unrelated code.
- Do not rename existing APIs unless explicitly requested.
- Do not modify generated files.
- Do not modify dependencies.
- Before editing multiple files, verify that each file is required.

## Agent Workflow

For non-trivial tasks:

1. Inspect relevant files only.
2. Identify the owner layer of the change.
3. Check existing patterns before introducing new ones.
4. Make the minimal implementation.
5. Run the relevant build/test target.
6. Report modified files and validation results.

Do not provide large explanations unless requested.

## Validation

Use `build.py` for normal configure, build, test, and clean operations.

```sh
python build.py configure
python build.py build
python build.py test
python build.py clean
```

Do not include lint in validation. The user performs lint checks manually.

## Build

Always use the Python build script — never invoke `cmake` directly.

```sh
python build.py configure                 # configure the default Debug build
python build.py build                     # build the default Debug target
python build.py test                      # build, then run pytest tests
python build.py clean                     # remove build, dist, cache, and native outputs
python build.py build --build-type Release
```

Build outputs land in `build/<build-type>/`, e.g. `build/debug/`.

## File / Directory Layout

- `include/...` — public headers (mirrors `src/`).
- `src/...` — implementation (`.cpp`).
- `templates/` — Jinja templates consumed by `build_script/reflection/`.
- `res/`, `test_env_res/` — runtime assets.
- `dependencies/` — vendored third-party (do not modify).
- `todos/` — per-layer todo lists.

Generated files:
- src/per_target/<target>/generated/
- include/per_target/<target>/generated/

Never edit generated files.

Header / source naming: `snake_case.hh` / `snake_case.cpp`. Header guards: `WBE_FILE_<UPPER_SNAKE>_HH`. One primary class per file; file name matches the class in `snake_case`.

## Special Member Functions (Rule of 6)

Classes that manage resources, ownership, or non-trivial state must explicitly follow the Rule of 6:

- Default constructor
- Destructor
- Copy constructor
- Copy assignment operator
- Move constructor
- Move assignment operator

Rules:
- If a class owns a resource, define or delete copy/move operations explicitly.
- Do not rely on compiler-generated copy/move operations for resource-owning types unless the behavior is verified to be correct.
- Prefer move semantics for ownership transfer.
- Copy operations must preserve ownership invariants and perform deep copies when required.
- Move operations must leave the moved-from object in a valid destructible state.
- Use `= delete` for unsupported operations instead of leaving accidental behavior.
- Use `= default` only when the generated implementation matches the intended ownership semantics.

## Naming

- `snake_case` for files, variables, functions, members. `PascalCase` for types. `UPPER_SNAKE` for macros and constants of macro-like nature.
- Function parameters: prefix `p_` (e.g. `p_allocator`, `p_buffer_size`). Local variables: no prefix. Member fields: no prefix.
- **No abbreviations** unless they are universally well-known. Examples:
  - Forbidden: `ci` (use `create_info`), `mgr` (use `manager`), `tex` (use `texture`), `cfg` (use `config` only if widely understood, else `configuration`).
  - Allowed well-known: `MPSC` (multiple producers, single consumer), `SPSC` (single producer, single consumer), `i`/`j`/`k` as for-loop indices, `id`, `uuid`, `gpu`, `cpu`, `os`, `vk` (Vulkan), `rma` (roughness-metallic-ao texture channel pack).
- If a name is too long, each word may be shortened to its first **≥4** letters. Examples: `initiate` → `init`, `information` → `info`, `allocator` → `alloc`; use shortening only when it remains unambiguous (`init`, `info`, `config`, `descr`).
- Preserve domain spellings already used in the codebase (e.g. test labels) even if unusual.

## Style

- C++23. `.clang-format` is authoritative; key rules:
  - `PointerAlignment: Left`, `ReferenceAlignment: Left` (`T* p`, `T& r`).
  - `ColumnLimit: 125`.
  - No short single-line forms: functions, lambdas, blocks, `if`, loops, `case`, `enum` all break to next line.
  - `AlwaysBreakTemplateDeclarations: Yes`.
  - `BreakStringLiterals: false` — long error-message string literals stay on one line.
- Use `WBE_NO_FALSE_SHARING` to pad hot atomics that risk contention.
- Prefer the engine's file system wrappers `Directory` / `Path` (in `platform/file_system/`) over raw `std::filesystem`. They are header-only thin wrappers around `std::filesystem` — use them in engine code; drop down to `std::filesystem` only inside their implementation or when an API genuinely requires it. Note: `Directory::get_dir_names()` returns by value, capture with `auto`.
- For unbounded counting semaphores, use `std::counting_semaphore<>` (max = `PTRDIFF_MAX`); do not pick a small `LeastMaxValue` unless you can prove the bound.

## Header / Source Separation

Non-trivial method implementations must be placed in `.cpp` files.

Allowed inline definitions in headers:
- Simple getters/setters.
- Trivial methods with a short, obvious implementation.
- Functions that require header definitions (e.g. templates).

Avoid placing complex logic, control flow, or dependency-heavy code in headers. Public headers should expose interfaces and declarations rather than implementation details.

## API Design

- **Prefer exposing classes and interfaces over free-function wrappers.** When a feature has internal state, a constructable context, or a small set of related operations, declare the class in the public header and expose its members. Do not hide it behind a file-local impl class wrapped by free functions in the .cpp. Internal helpers, anonymous-namespace utilities, and detail types stay in the `.cpp`.
- **Name derived implementations with the interface (or its abbreviation) as a prefix.** For example, `RenderObject` → `ROImage`, `ROGraphicsPipelineVK`; `Renderer` → `RendererVK`; `RenderTask` → `RTRunGraphicsPipelineVK`. Pick a short, consistent abbreviation per interface and use it for all derived types.

## Documentation

Use Doxygen for C++ and Slang.

Required:
- Public/protected classes, structs, fields, functions.

Not required:
- Private members.
- Overrides unless behavior differs.

Document contracts, ownership, threading, and errors; do not restate signatures.

## Python Scripts

- Do not create Python environments manually. Assume the current environment is capable for development; if it is not, pause, notify the user, and let the user resolve it.
- All function parameters and return values must have type annotations. Use `-> None` explicitly for procedures.
- Prefer concrete generics (`list[str]`, `dict[str, Any]`) over bare `list` / `dict`. Use `from typing import Any, Callable` etc. when needed.
- Annotate non-trivial local variables whose type cannot be obviously inferred (e.g. empty containers: `result: list[str] = []`).
- Use PEP 604 unions (`X | None`) rather than `Optional[X]`.

## Tests

Run tests with `python build.py test`.

## Geometry Output

- `compile_mesh` emits runtime mesh dictionaries with `geometry_path` and `geometry_sections`; it must not emit `vertices_data` or `indices_data`.
- Geometry sidecar binaries are raw section payloads only: `float32` for `position`, `normal`, `tangent`, `bitangent`, and `uv`; `uint32` for `index`.
- Assimp tangent-space generation is enabled. Preserve tangent and bitangent export when changing import flags or intermediate vertex fields.
- `geometry_output_dir` is source-only and resource-root-relative. Do not leak it into runtime resource dictionaries.

## Material Output

- `compile` returns the mesh resource first, followed by its material resources.
- `compile_materials` emits final runtime material dictionaries. Texture bindings use `texture_role`; inline images use `path` and
  set `flip_v` to `True`.
- Keep material texture normalization in this package. Callers such as the engine ACP adapter must not reshape compiler output.

## Reflection / Codegen

- All C++ header code are scanned by `build_script/reflection/metaparser.py`.
- Generated artifacts live in `*.gen.*` files; regenerated automatically each build. Do not edit by hand.
- Templates for codegen live in `templates/*.jinja`.
- `generate.json` supports `${name}` replacement in `output_name`, `template`, `out_dir`, and nested string values under `data`. Per-entry `params` override built-ins; bu
ilt-ins include `build_target`, `build_dir`, `binary_dir`, `root_dir`, `include_dir`, and `source_dir`.
