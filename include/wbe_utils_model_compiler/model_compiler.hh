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
#ifndef WBE_FILE_MODEL_COMPILER_HH
#define WBE_FILE_MODEL_COMPILER_HH

#include <filesystem>
#include <string>

#include <pybind11/pybind11.h>

namespace wbe::model_compiler
{
/**
 * Compiles external model assets into White Bird Engine resource dictionaries.
 *
 * The compiler owns no long-lived native resources. Source assets are loaded per call, converted to an internal
 * intermediate representation, and returned as Python-compatible pybind11 objects.
 */
class ModelCompiler
{
public:
    ModelCompiler() = default;
    ~ModelCompiler() = default;
    ModelCompiler(const ModelCompiler& p_other) = default;
    ModelCompiler& operator=(const ModelCompiler& p_other) = default;
    ModelCompiler(ModelCompiler&& p_other) noexcept = default;
    ModelCompiler& operator=(ModelCompiler&& p_other) noexcept = default;

    /**
     * Compile mesh geometry into a White Bird Engine mesh resource dictionary.
     *
     * Source-space positions and direction vectors are converted to the target space. Each space must assign up,
     * right, and front to three distinct signed axes.
     *
     * @throws std::invalid_argument If the scale is not finite or either coordinate-space declaration is invalid.
     */
    pybind11::dict compile_mesh(
        const std::filesystem::path& p_source_path,
        const std::string& p_resource_id,
        const pybind11::list& p_graphics_pipeline_ids,
        const std::string& p_texture_output_dir,
        const std::filesystem::path& p_geometry_output_dir,
        const std::string& p_geometry_path_prefix,
        float p_vertex_position_scale = 1.0F,
        const std::string& p_source_up_direction = "y",
        const std::string& p_source_right_direction = "x",
        const std::string& p_source_front_direction = "z",
        const std::string& p_target_up_direction = "y",
        const std::string& p_target_right_direction = "x",
        const std::string& p_target_front_direction = "z",
        bool p_combine_nodes = false) const;

    /** Compile source materials into White Bird Engine material resource dictionaries. */
    pybind11::list compile_materials(
        const std::filesystem::path& p_source_path,
        const std::string& p_resource_id,
        const pybind11::list& p_graphics_pipeline_ids,
        const pybind11::list& p_masked_graphics_pipeline_ids,
        const std::string& p_texture_output_dir,
        const std::filesystem::path& p_texture_output_root) const;
};
}

#endif
