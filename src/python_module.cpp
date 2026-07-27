/* Copyright 2025 OppositeNor
 
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
  
       http://www.apache.org/licenses/LICENSE-2.0
  
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
#include "wbe_build_utils_mesh_compiler/mesh_compiler.hh"

#include <filesystem>
#include <string>

#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(_native, p_module)
{
    p_module.doc() = "Native backend for the White Bird Engine mesh compiler.";

    p_module.def(
        "compile_mesh",
        [](const std::string& p_source_path,
           const std::string& p_resource_id,
           const py::list& p_graphics_pipeline_ids,
           const std::string& p_texture_output_dir) -> py::dict {
            const wbe::mesh_compiler::MeshCompiler compiler;
            return compiler.compile_mesh(std::filesystem::path(p_source_path), p_resource_id, p_graphics_pipeline_ids, p_texture_output_dir);
        },
        py::arg("source_path"),
        py::arg("resource_id"),
        py::arg("graphics_pipeline_ids"),
        py::arg("texture_output_dir"));

    p_module.def(
        "compile_materials",
        [](const std::string& p_source_path,
           const std::string& p_resource_id,
           const py::list& p_graphics_pipeline_ids,
           const std::string& p_texture_output_dir) -> py::list {
            const wbe::mesh_compiler::MeshCompiler compiler;
            return compiler.compile_materials(std::filesystem::path(p_source_path), p_resource_id, p_graphics_pipeline_ids, p_texture_output_dir);
        },
        py::arg("source_path"),
        py::arg("resource_id"),
        py::arg("graphics_pipeline_ids"),
        py::arg("texture_output_dir"));
}
