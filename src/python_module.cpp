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
#include "wbe_utils_model_compiler/model_compiler.hh"

#include <filesystem>
#include <string>

#include <pybind11/pybind11.h>

namespace py = pybind11;

PYBIND11_MODULE(_native, p_module)
{
    p_module.doc() = "Native backend for the White Bird Engine model compiler.";

    p_module.def(
        "compile_mesh",
        [](const std::string& p_source_path,
           const std::string& p_resource_id,
           const py::list& p_graphics_pipeline_ids,
           const std::string& p_texture_output_dir,
           const std::string& p_geometry_output_dir,
           const std::string& p_geometry_path_prefix,
           float p_vertex_position_scale,
           const std::string& p_source_up_direction,
           const std::string& p_source_right_direction,
           const std::string& p_source_front_direction,
           const std::string& p_target_up_direction,
           const std::string& p_target_right_direction,
           const std::string& p_target_front_direction) -> py::dict {
            const wbe::model_compiler::ModelCompiler compiler;
            return compiler.compile_mesh(std::filesystem::path(p_source_path),
                p_resource_id,
                p_graphics_pipeline_ids,
                p_texture_output_dir,
                std::filesystem::path(p_geometry_output_dir),
                p_geometry_path_prefix,
                p_vertex_position_scale,
                p_source_up_direction,
                p_source_right_direction,
                p_source_front_direction,
                p_target_up_direction,
                p_target_right_direction,
                p_target_front_direction);
        },
        py::arg("source_path"),
        py::arg("resource_id"),
        py::arg("graphics_pipeline_ids"),
        py::arg("texture_output_dir"),
        py::arg("geometry_output_dir"),
        py::arg("geometry_path_prefix"),
        py::arg("vertex_position_scale") = 1.0F,
        py::arg("source_up_direction") = "y",
        py::arg("source_right_direction") = "x",
        py::arg("source_front_direction") = "z",
        py::arg("target_up_direction") = "y",
        py::arg("target_right_direction") = "x",
        py::arg("target_front_direction") = "z");

    p_module.def(
        "compile_materials",
        [](const std::string& p_source_path,
           const std::string& p_resource_id,
           const py::list& p_graphics_pipeline_ids,
           const py::list& p_masked_graphics_pipeline_ids,
           const std::string& p_texture_output_dir) -> py::list {
            const wbe::model_compiler::ModelCompiler compiler;
            return compiler.compile_materials(std::filesystem::path(p_source_path),
                p_resource_id,
                p_graphics_pipeline_ids,
                p_masked_graphics_pipeline_ids,
                p_texture_output_dir);
        },
        py::arg("source_path"),
        py::arg("resource_id"),
        py::arg("graphics_pipeline_ids"),
        py::arg("masked_graphics_pipeline_ids"),
        py::arg("texture_output_dir"));
}
