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
#include <vector>

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
     * @param p_flip_v Keep Assimp's bottom-left UVs instead of the default top-left output.
     * @throws std::invalid_argument If the scale is not finite or either coordinate-space declaration is invalid.
     */
    pybind11::list compile_mesh(
        const std::filesystem::path& p_source_path,
        const std::string& p_resource_id,
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
        bool p_combine_nodes = false,
        bool p_flip_v = false) const;

    /**
     * @brief Stack model sources into shared static meshes, preserving each node's transform.
     * @param p_source_paths Non-empty ordered source list. Multiple sources receive distinct ID prefixes.
     * @throws std::runtime_error If the source list is empty or a model cannot be loaded.
     */
    pybind11::list compile_static_geometry(
        const std::vector<std::filesystem::path>& p_source_paths,
        const std::string& p_resource_id,
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
        bool p_flip_v = false) const;

    /**
     * @brief Run independent texture requests on a bounded thread pool and join every job before returning.
     * @param p_compile_texture Thread-safe Python callback; expensive native work should release the GIL.
     * @param p_requests Requests with distinct destination paths, retained until every job finishes.
     * @param p_worker_count Positive maximum number of concurrent callbacks.
     * @throws std::runtime_error If the worker count is zero. Callback errors propagate after all jobs finish.
     */
    void compile_textures(const pybind11::function& p_compile_texture,
        const pybind11::list& p_requests,
        unsigned int p_worker_count) const;

    /**
     * @brief Compile source materials into material resource dictionaries.
     */
    pybind11::list compile_materials(
        const std::filesystem::path& p_source_path,
        const std::string& p_resource_id,
        const std::string& p_texture_output_dir,
        const std::filesystem::path& p_texture_output_root) const;
};
}

#endif
