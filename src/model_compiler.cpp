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

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <assimp/Importer.hpp>
#include <assimp/GltfMaterial.h>
#include <assimp/material.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <pybind11/pybind11.h>

#define STB_IMAGE_IMPLEMENTATION
#include <stb_image.h>
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include <stb_image_write.h>

namespace py = pybind11;

namespace wbe::model_compiler
{
namespace
{
struct IntermediateVertex
{
    std::array<float, 3> position = {0.0F, 0.0F, 0.0F};
    std::array<float, 2> uv = {0.0F, 0.0F};
    std::array<float, 3> normal = {0.0F, 0.0F, 0.0F};
    std::array<float, 3> tangent = {0.0F, 0.0F, 0.0F};
    std::array<float, 3> bitangent = {0.0F, 0.0F, 0.0F};
    std::vector<std::pair<int, float>> bones;
};

struct IntermediateSubmesh
{
    std::string id;
    std::vector<IntermediateVertex> vertices;
    std::vector<unsigned int> indices;
    std::string material_id;
    bool has_material = false;
    bool has_uv = false;
    bool has_normal = false;
    bool has_tangent_space = false;
};

struct IntermediateMaterialTexture
{
    std::string texture_key;
    std::string file;
    std::string path;
    std::string color_space;
    int channel_count = 4;
};

struct IntermediateMaterial
{
    std::string id;
    std::vector<IntermediateMaterialTexture> textures;
    bool masked = false;
};

struct IntermediateScene
{
    std::vector<IntermediateSubmesh> submeshes;
    std::vector<IntermediateMaterial> materials;
};

struct AxisDirection
{
    size_t axis = 0;
    float sign = 1.0F;
};

struct CoordinateSpace
{
    AxisDirection up;
    AxisDirection right;
    AxisDirection front;
};

struct VertexTransform
{
    std::array<std::array<float, 3>, 3> basis = {};
    float position_scale = 1.0F;
    bool reverse_winding = false;
};

AxisDirection parse_axis_direction(const std::string& p_direction)
{
    size_t character_index = 0;
    float sign = 1.0F;
    if (!p_direction.empty() && (p_direction[0] == '+' || p_direction[0] == '-'))
    {
        sign = p_direction[0] == '-' ? -1.0F : 1.0F;
        character_index = 1;
    }
    if (p_direction.size() != character_index + 1)
    {
        throw std::invalid_argument("Model direction must be one of x, y, z, +x, +y, +z, -x, -y, or -z: " + p_direction);
    }

    const char axis_name = p_direction[character_index];
    if (axis_name < 'x' || axis_name > 'z')
    {
        throw std::invalid_argument("Model direction must be one of x, y, z, +x, +y, +z, -x, -y, or -z: " + p_direction);
    }
    return AxisDirection{.axis = static_cast<size_t>(axis_name - 'x'), .sign = sign};
}

CoordinateSpace make_coordinate_space(const std::string& p_up_direction,
    const std::string& p_right_direction,
    const std::string& p_front_direction,
    const std::string& p_space_name)
{
    const CoordinateSpace result{
        .up = parse_axis_direction(p_up_direction),
        .right = parse_axis_direction(p_right_direction),
        .front = parse_axis_direction(p_front_direction),
    };
    if (result.up.axis == result.right.axis || result.up.axis == result.front.axis || result.right.axis == result.front.axis)
    {
        throw std::invalid_argument(
            "Model " + p_space_name + " up, right, and front directions must use three different axes.");
    }
    return result;
}

float determinant(const std::array<std::array<float, 3>, 3>& p_matrix)
{
    return p_matrix[0][0] * (p_matrix[1][1] * p_matrix[2][2] - p_matrix[1][2] * p_matrix[2][1]) -
           p_matrix[0][1] * (p_matrix[1][0] * p_matrix[2][2] - p_matrix[1][2] * p_matrix[2][0]) +
           p_matrix[0][2] * (p_matrix[1][0] * p_matrix[2][1] - p_matrix[1][1] * p_matrix[2][0]);
}

void add_axis_mapping(std::array<std::array<float, 3>, 3>& p_basis,
    const AxisDirection& p_source_direction,
    const AxisDirection& p_target_direction)
{
    p_basis[p_target_direction.axis][p_source_direction.axis] = p_source_direction.sign * p_target_direction.sign;
}

VertexTransform make_vertex_transform(float p_position_scale,
    const std::string& p_source_up_direction,
    const std::string& p_source_right_direction,
    const std::string& p_source_front_direction,
    const std::string& p_target_up_direction,
    const std::string& p_target_right_direction,
    const std::string& p_target_front_direction)
{
    if (!std::isfinite(p_position_scale))
    {
        throw std::invalid_argument("scale_vertex_pos must be finite.");
    }

    const CoordinateSpace source =
        make_coordinate_space(p_source_up_direction, p_source_right_direction, p_source_front_direction, "source_space");
    const CoordinateSpace target =
        make_coordinate_space(p_target_up_direction, p_target_right_direction, p_target_front_direction, "target_space");

    VertexTransform result;
    result.position_scale = p_position_scale;
    add_axis_mapping(result.basis, source.up, target.up);
    add_axis_mapping(result.basis, source.right, target.right);
    add_axis_mapping(result.basis, source.front, target.front);
    result.reverse_winding = determinant(result.basis) < 0.0F;
    return result;
}

std::array<float, 3> transform_vector(const std::array<float, 3>& p_value, const VertexTransform& p_transform)
{
    std::array<float, 3> result = {};
    for (size_t output_axis = 0; output_axis < result.size(); ++output_axis)
    {
        for (size_t input_axis = 0; input_axis < p_value.size(); ++input_axis)
        {
            result[output_axis] += p_transform.basis[output_axis][input_axis] * p_value[input_axis];
        }
    }
    return result;
}

py::dict make_vec3(const std::array<float, 3>& p_value)
{
    py::dict result;
    result["x"] = p_value[0];
    result["y"] = p_value[1];
    result["z"] = p_value[2];
    return result;
}

py::dict make_uv(const std::array<float, 2>& p_value)
{
    py::dict result;
    result["u"] = p_value[0];
    result["v"] = p_value[1];
    return result;
}

py::object make_bones(const std::vector<std::pair<int, float>>& p_bones)
{
    if (p_bones.empty())
    {
        return py::none();
    }

    py::list result;
    for (const auto& [bone_index, bone_weight] : p_bones)
    {
        py::dict bone;
        bone["index"] = bone_index;
        bone["weight"] = bone_weight;
        result.append(bone);
    }
    return result;
}

std::string generated_resource_id_for(const std::string& p_resource_id, const std::string& p_resource_type, const std::string& p_local_id)
{
    return p_resource_id + "." + p_resource_type + "." + p_local_id;
}

std::string material_local_id_for(const aiMaterial* p_material, unsigned int p_material_index)
{
    aiString material_name;
    if (p_material != nullptr && p_material->Get(AI_MATKEY_NAME, material_name) == AI_SUCCESS && material_name.length > 0)
    {
        return material_name.C_Str();
    }
    return std::to_string(p_material_index);
}

std::string material_id_for(const aiMaterial* p_material, const std::string& p_resource_id, unsigned int p_material_index)
{
    return generated_resource_id_for(p_resource_id, "material", material_local_id_for(p_material, p_material_index));
}

std::string submesh_local_id_for(const aiMesh* p_mesh, unsigned int p_mesh_index)
{
    if (p_mesh->mName.length > 0)
    {
        return p_mesh->mName.C_Str();
    }
    return std::to_string(p_mesh_index);
}

std::string submesh_id_for(const aiMesh* p_mesh, const std::string& p_resource_id, unsigned int p_mesh_index)
{
    return generated_resource_id_for(p_resource_id, "submesh", submesh_local_id_for(p_mesh, p_mesh_index));
}

std::string texture_output_path(const aiString& p_texture_path, const std::string& p_texture_output_dir)
{
    const std::filesystem::path source_path(p_texture_path.C_Str());
    if (p_texture_output_dir.empty())
    {
        return source_path.generic_string();
    }

    const std::filesystem::path output_dir(p_texture_output_dir);
    if (output_dir.is_absolute())
    {
        return source_path.filename().generic_string();
    }
    return (output_dir / source_path.filename()).generic_string();
}

void stage_texture_file(const std::filesystem::path& p_source_directory,
    const aiString& p_texture_path,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_texture_output_root,
    IntermediateMaterialTexture& p_texture)
{
    if (p_texture_output_root.empty() || p_texture_output_dir.empty() || p_texture_path.C_Str()[0] == '*')
    {
        return;
    }

    const std::filesystem::path source_texture_path(p_texture_path.C_Str());
    const std::filesystem::path resolved_source_path =
        source_texture_path.is_absolute() ? source_texture_path : p_source_directory / source_texture_path;
    const std::filesystem::path relative_output_path = texture_output_path(p_texture_path, p_texture_output_dir);
    const std::filesystem::path output_path = p_texture_output_root / relative_output_path;

    std::filesystem::create_directories(output_path.parent_path());

    std::error_code error_code;
    std::filesystem::copy_file(
        resolved_source_path, output_path, std::filesystem::copy_options::overwrite_existing, error_code);
    if (error_code)
    {
        throw std::runtime_error(
            "Failed to copy material texture: " + resolved_source_path.generic_string() + " -> " + output_path.generic_string());
    }

    p_texture.file = std::filesystem::absolute(output_path).generic_string();
    p_texture.path = relative_output_path.generic_string();
}

bool add_texture(
    const std::filesystem::path& p_source_directory,
    const aiMaterial* p_material,
    aiTextureType p_texture_type,
    const std::string& p_texture_key,
    const std::string& p_color_space,
    int p_channel_count,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_texture_output_root,
    std::vector<IntermediateMaterialTexture>& p_textures)
{
    aiString texture_path;
    if (p_material->GetTexture(p_texture_type, 0, &texture_path) != AI_SUCCESS || texture_path.length == 0)
    {
        return false;
    }

    p_textures.push_back(IntermediateMaterialTexture{
        .texture_key = p_texture_key,
        .file = std::filesystem::path(texture_path.C_Str()).generic_string(),
        .path = texture_output_path(texture_path, p_texture_output_dir),
        .color_space = p_color_space,
        .channel_count = p_channel_count,
    });
    stage_texture_file(p_source_directory, texture_path, p_texture_output_dir, p_texture_output_root, p_textures.back());
    return true;
}

bool get_texture_path(const aiMaterial* p_material, aiTextureType p_texture_type, std::filesystem::path& p_path)
{
    aiString texture_path;
    if (p_material->GetTexture(p_texture_type, 0, &texture_path) != AI_SUCCESS || texture_path.length == 0 ||
        texture_path.C_Str()[0] == '*')
    {
        return false;
    }
    p_path = std::filesystem::path(texture_path.C_Str());
    return true;
}

void repack_rma_texture(const std::filesystem::path& p_source_directory,
    const std::filesystem::path& p_packed_metallic_roughness_path,
    const std::filesystem::path& p_metalness_path,
    const std::filesystem::path& p_roughness_path,
    const std::filesystem::path& p_occlusion_path,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_texture_output_root,
    IntermediateMaterialTexture& p_texture)
{
    std::filesystem::path source_texture_path = p_packed_metallic_roughness_path;
    if (source_texture_path.empty())
    {
        source_texture_path = !p_metalness_path.empty()
                                  ? p_metalness_path
                                  : (!p_roughness_path.empty() ? p_roughness_path : p_occlusion_path);
    }
    const std::filesystem::path source_path = p_source_directory / source_texture_path;
    int source_width = 0;
    int source_height = 0;
    int source_channels = 0;
    unsigned char* source_pixels =
        stbi_load(source_path.string().c_str(), &source_width, &source_height, &source_channels, 4);
    if (source_pixels == nullptr)
    {
        throw std::runtime_error(
            "Failed to decode material texture: " + source_path.string() + ". " + stbi_failure_reason());
    }

    const std::filesystem::path roughness_source_path = p_source_directory / p_roughness_path;
    const std::filesystem::path metalness_source_path = p_source_directory / p_metalness_path;
    const std::filesystem::path occlusion_source_path = p_source_directory / p_occlusion_path;
    int roughness_width = 0;
    int roughness_height = 0;
    int roughness_channels = 0;
    unsigned char* roughness_pixels = nullptr;
    if (!p_roughness_path.empty() && p_roughness_path != source_texture_path)
    {
        roughness_pixels = stbi_load(
            roughness_source_path.string().c_str(), &roughness_width, &roughness_height, &roughness_channels, 4);
        if (roughness_pixels == nullptr)
        {
            stbi_image_free(source_pixels);
            throw std::runtime_error(
                "Failed to decode material texture: " + roughness_source_path.string() + ". " + stbi_failure_reason());
        }
    }
    int metalness_width = 0;
    int metalness_height = 0;
    int metalness_channels = 0;
    unsigned char* metalness_pixels = nullptr;
    if (!p_metalness_path.empty() && p_metalness_path != source_texture_path)
    {
        metalness_pixels =
            stbi_load(metalness_source_path.string().c_str(), &metalness_width, &metalness_height, &metalness_channels, 4);
        if (metalness_pixels == nullptr)
        {
            stbi_image_free(source_pixels);
            stbi_image_free(roughness_pixels);
            throw std::runtime_error(
                "Failed to decode material texture: " + metalness_source_path.string() + ". " + stbi_failure_reason());
        }
    }
    int occlusion_width = 0;
    int occlusion_height = 0;
    int occlusion_channels = 0;
    unsigned char* occlusion_pixels = nullptr;
    if (!p_occlusion_path.empty() && p_occlusion_path != source_texture_path)
    {
        occlusion_pixels = stbi_load(
            occlusion_source_path.string().c_str(), &occlusion_width, &occlusion_height, &occlusion_channels, 4);
        if (occlusion_pixels == nullptr)
        {
            stbi_image_free(source_pixels);
            stbi_image_free(roughness_pixels);
            stbi_image_free(metalness_pixels);
            throw std::runtime_error(
                "Failed to decode material texture: " + occlusion_source_path.string() + ". " + stbi_failure_reason());
        }
    }
    if ((roughness_pixels != nullptr && (roughness_width != source_width || roughness_height != source_height)) ||
        (metalness_pixels != nullptr && (metalness_width != source_width || metalness_height != source_height)) ||
        (occlusion_pixels != nullptr && (occlusion_width != source_width || occlusion_height != source_height)))
    {
        stbi_image_free(source_pixels);
        stbi_image_free(roughness_pixels);
        stbi_image_free(metalness_pixels);
        stbi_image_free(occlusion_pixels);
        throw std::runtime_error("Roughness, metallic, and occlusion textures must have matching dimensions.");
    }

    std::vector<unsigned char> rma_pixels(static_cast<size_t>(source_width) * static_cast<size_t>(source_height) * 3U);
    for (int pixel_index = 0; pixel_index < source_width * source_height; ++pixel_index)
    {
        const unsigned char* source_pixel = source_pixels + pixel_index * 4;
        const size_t output_index = static_cast<size_t>(pixel_index) * 3U;
        if (!p_packed_metallic_roughness_path.empty())
        {
            rma_pixels[output_index] = source_pixel[1];
            rma_pixels[output_index + 1U] = source_pixel[2];
        }
        else
        {
            rma_pixels[output_index] = 255U;
            if (!p_roughness_path.empty())
            {
                rma_pixels[output_index] = roughness_pixels != nullptr ? roughness_pixels[pixel_index * 4] : source_pixel[0];
            }
            rma_pixels[output_index + 1U] = 0U;
            if (!p_metalness_path.empty())
            {
                rma_pixels[output_index + 1U] = metalness_pixels != nullptr ? metalness_pixels[pixel_index * 4] : source_pixel[0];
            }
        }
        rma_pixels[output_index + 2U] = 255U;
        if (!p_occlusion_path.empty())
        {
            rma_pixels[output_index + 2U] = occlusion_pixels != nullptr ? occlusion_pixels[pixel_index * 4] : source_pixel[0];
        }
    }

    const std::string output_name = source_path.stem().string() + "_rma.png";
    const std::filesystem::path relative_output_path = std::filesystem::path(p_texture_output_dir) / output_name;
    const std::filesystem::path output_path = p_texture_output_root / relative_output_path;
    std::filesystem::create_directories(output_path.parent_path());
    if (stbi_write_png(
            output_path.string().c_str(), source_width, source_height, 3, rma_pixels.data(), source_width * 3) == 0)
    {
        stbi_image_free(source_pixels);
        stbi_image_free(roughness_pixels);
        stbi_image_free(metalness_pixels);
        stbi_image_free(occlusion_pixels);
        throw std::runtime_error("Failed to write repacked RMA texture: " + output_path.string() + ".");
    }

    stbi_image_free(source_pixels);
    stbi_image_free(roughness_pixels);
    stbi_image_free(metalness_pixels);
    stbi_image_free(occlusion_pixels);
    p_texture.file = std::filesystem::absolute(output_path).generic_string();
    p_texture.path = relative_output_path.generic_string();
}

bool add_rma_texture(const aiMaterial* p_material,
    const std::filesystem::path& p_source_directory,
    bool p_uses_gltf_texture_conventions,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_texture_output_root,
    std::vector<IntermediateMaterialTexture>& p_textures)
{
    std::filesystem::path packed_metallic_roughness_path;
    std::filesystem::path metalness_path;
    std::filesystem::path roughness_path;
    std::filesystem::path occlusion_path;
    const bool has_packed_metallic_roughness =
        get_texture_path(p_material, aiTextureType_GLTF_METALLIC_ROUGHNESS, packed_metallic_roughness_path);
    const bool has_metalness =
        !has_packed_metallic_roughness && get_texture_path(p_material, aiTextureType_METALNESS, metalness_path);
    const bool has_roughness =
        !has_packed_metallic_roughness && get_texture_path(p_material, aiTextureType_DIFFUSE_ROUGHNESS, roughness_path);
    bool has_occlusion = get_texture_path(p_material, aiTextureType_AMBIENT_OCCLUSION, occlusion_path);
    if (!has_occlusion && p_uses_gltf_texture_conventions)
    {
        has_occlusion = get_texture_path(p_material, aiTextureType_LIGHTMAP, occlusion_path);
    }
    if (!has_packed_metallic_roughness && !has_metalness && !has_roughness && !has_occlusion)
    {
        return false;
    }

    std::filesystem::path source_texture_path = packed_metallic_roughness_path;
    if (source_texture_path.empty())
    {
        source_texture_path = has_metalness ? metalness_path : (has_roughness ? roughness_path : occlusion_path);
    }
    p_textures.push_back(IntermediateMaterialTexture{
        .texture_key = "rma",
        .file = source_texture_path.generic_string(),
        .path = (std::filesystem::path(p_texture_output_dir) / source_texture_path.filename()).generic_string(),
        .color_space = "rgb",
        .channel_count = 3,
    });
    if (!p_texture_output_root.empty())
    {
        repack_rma_texture(p_source_directory,
            packed_metallic_roughness_path,
            metalness_path,
            roughness_path,
            occlusion_path,
            p_texture_output_dir,
            p_texture_output_root,
            p_textures.back());
    }
    return true;
}

void apply_bones(const aiMesh* p_mesh, std::vector<IntermediateVertex>& p_vertices)
{
    for (unsigned int bone_index = 0; bone_index < p_mesh->mNumBones; ++bone_index)
    {
        const aiBone* bone = p_mesh->mBones[bone_index];
        for (unsigned int weight_index = 0; weight_index < bone->mNumWeights; ++weight_index)
        {
            const aiVertexWeight& weight = bone->mWeights[weight_index];
            if (weight.mVertexId >= p_vertices.size())
            {
                continue;
            }
            auto& vertex_bones = p_vertices[weight.mVertexId].bones;
            if (vertex_bones.size() < 4)
            {
                vertex_bones.emplace_back(static_cast<int>(bone_index), weight.mWeight);
            }
        }
    }
}

IntermediateSubmesh import_submesh(const aiScene* p_scene,
    const aiMesh* p_mesh,
    const std::string& p_resource_id,
    unsigned int p_mesh_index,
    const VertexTransform& p_transform)
{
    IntermediateSubmesh result;
    result.id = submesh_id_for(p_mesh, p_resource_id, p_mesh_index);
    result.vertices.reserve(p_mesh->mNumVertices);
    result.indices.reserve(p_mesh->mNumFaces * 3);
    result.has_uv = p_mesh->HasTextureCoords(0);
    result.has_normal = p_mesh->HasNormals();
    result.has_tangent_space = p_mesh->HasTangentsAndBitangents();

    if (p_mesh->mMaterialIndex < p_scene->mNumMaterials)
    {
        result.has_material = true;
        result.material_id = material_id_for(p_scene->mMaterials[p_mesh->mMaterialIndex], p_resource_id, p_mesh->mMaterialIndex);
    }

    for (unsigned int vertex_index = 0; vertex_index < p_mesh->mNumVertices; ++vertex_index)
    {
        IntermediateVertex vertex;
        const aiVector3D& position = p_mesh->mVertices[vertex_index];
        vertex.position = transform_vector({position.x, position.y, position.z}, p_transform);
        for (float& component : vertex.position)
        {
            component *= p_transform.position_scale;
        }

        if (result.has_uv)
        {
            const aiVector3D& uv = p_mesh->mTextureCoords[0][vertex_index];
            vertex.uv = {uv.x, uv.y};
        }

        if (result.has_normal)
        {
            const aiVector3D& normal = p_mesh->mNormals[vertex_index];
            vertex.normal = transform_vector({normal.x, normal.y, normal.z}, p_transform);
        }
        if (result.has_tangent_space)
        {
            const aiVector3D& tangent = p_mesh->mTangents[vertex_index];
            const aiVector3D& bitangent = p_mesh->mBitangents[vertex_index];
            vertex.tangent = transform_vector({tangent.x, tangent.y, tangent.z}, p_transform);
            vertex.bitangent = transform_vector({bitangent.x, bitangent.y, bitangent.z}, p_transform);
        }
        result.vertices.push_back(vertex);
    }

    apply_bones(p_mesh, result.vertices);

    for (unsigned int face_index = 0; face_index < p_mesh->mNumFaces; ++face_index)
    {
        const aiFace& face = p_mesh->mFaces[face_index];
        for (unsigned int index_index = 0; index_index < face.mNumIndices; ++index_index)
        {
            result.indices.push_back(face.mIndices[index_index]);
        }
    }

    if (p_transform.reverse_winding)
    {
        for (size_t index = 0; index + 2 < result.indices.size(); index += 3)
        {
            std::swap(result.indices[index + 1], result.indices[index + 2]);
        }
    }

    return result;
}

IntermediateMaterial import_material(
    const aiMaterial* p_material,
    const std::string& p_resource_id,
    unsigned int p_material_index,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_source_directory,
    const std::filesystem::path& p_texture_output_root,
    bool p_uses_gltf_texture_conventions)
{
    IntermediateMaterial result;
    result.id = material_id_for(p_material, p_resource_id, p_material_index);
    aiString alpha_mode;
    result.masked =
        p_material->Get(AI_MATKEY_GLTF_ALPHAMODE, alpha_mode) == AI_SUCCESS && std::string(alpha_mode.C_Str()) == "MASK";

    if (!add_texture(
            p_source_directory, p_material, aiTextureType_BASE_COLOR, "albedo", "srgb", 4, p_texture_output_dir, p_texture_output_root, result.textures))
    {
        add_texture(
            p_source_directory, p_material, aiTextureType_DIFFUSE, "albedo", "srgb", 4, p_texture_output_dir, p_texture_output_root, result.textures);
    }

    if (!add_texture(
            p_source_directory, p_material, aiTextureType_NORMALS, "normal", "rgb", 3, p_texture_output_dir, p_texture_output_root, result.textures))
    {
        add_texture(
            p_source_directory, p_material, aiTextureType_HEIGHT, "normal", "rgb", 3, p_texture_output_dir, p_texture_output_root, result.textures);
    }

    add_rma_texture(p_material,
        p_source_directory,
        p_uses_gltf_texture_conventions,
        p_texture_output_dir,
        p_texture_output_root,
        result.textures);

    return result;
}

IntermediateScene import_scene(const std::filesystem::path& p_source_path,
    const std::string& p_resource_id,
    const std::string& p_texture_output_dir,
    const VertexTransform& p_transform,
    const std::filesystem::path& p_texture_output_root)
{
    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        p_source_path.string(),
        aiProcess_Triangulate | aiProcess_GenNormals | aiProcess_CalcTangentSpace | aiProcess_JoinIdenticalVertices | aiProcess_ImproveCacheLocality);
    if (scene == nullptr)
    {
        throw std::runtime_error("Assimp failed to load mesh asset: " + std::string(importer.GetErrorString()));
    }

    IntermediateScene result;
    result.submeshes.reserve(scene->mNumMeshes);
    result.materials.reserve(scene->mNumMaterials);
    std::string source_extension = p_source_path.extension().string();
    std::ranges::transform(source_extension, source_extension.begin(), [](unsigned char p_character) {
        return static_cast<char>(std::tolower(p_character));
    });
    const bool uses_gltf_texture_conventions = source_extension == ".gltf" || source_extension == ".glb";

    for (unsigned int material_index = 0; material_index < scene->mNumMaterials; ++material_index)
    {
        result.materials.push_back(import_material(scene->mMaterials[material_index],
            p_resource_id,
            material_index,
            p_texture_output_dir,
            p_source_path.parent_path(),
            p_texture_output_root,
            uses_gltf_texture_conventions));
    }

    for (unsigned int mesh_index = 0; mesh_index < scene->mNumMeshes; ++mesh_index)
    {
        result.submeshes.push_back(
            import_submesh(scene, scene->mMeshes[mesh_index], p_resource_id, mesh_index, p_transform));
    }

    return result;
}

py::list pipeline_ids_from(const py::list& p_graphics_pipeline_ids)
{
    py::list result;
    for (const py::handle item : p_graphics_pipeline_ids)
    {
        result.append(py::str(item));
    }
    return result;
}

py::dict make_geometry_section(const std::string& p_slot, size_t p_start, size_t p_size, const std::string& p_type)
{
    py::dict result;
    result["slot"] = p_slot;
    result["start"] = p_start;
    result["size"] = p_size;
    result["type"] = p_type;
    return result;
}

std::string sanitize_file_stem(const std::string& p_value)
{
    std::string result;
    result.reserve(p_value.size());
    for (unsigned char character : p_value)
    {
        if (std::isalnum(character) != 0 || character == '.' || character == '_' || character == '-')
        {
            result.push_back(static_cast<char>(character));
        }
        else
        {
            result.push_back('_');
        }
    }
    return result.empty() ? "submesh" : result;
}

void write_bytes(std::ofstream& p_output_file, const void* p_data, size_t p_size, size_t& p_offset, const std::filesystem::path& p_output_path)
{
    if (p_size == 0)
    {
        return;
    }
    p_output_file.write(static_cast<const char*>(p_data), static_cast<std::streamsize>(p_size));
    if (!p_output_file)
    {
        throw std::runtime_error("Failed to write model geometry binary: " + p_output_path.generic_string());
    }
    p_offset += p_size;
}

void write_vec3_section(std::ofstream& p_output_file,
    py::list& p_sections,
    const std::filesystem::path& p_output_path,
    size_t& p_offset,
    const std::string& p_slot,
    const std::vector<IntermediateVertex>& p_vertices,
    const std::array<float, 3> IntermediateVertex::* p_member,
    bool p_enabled)
{
    if (!p_enabled)
    {
        return;
    }
    const size_t start = p_offset;
    for (const IntermediateVertex& vertex : p_vertices)
    {
        const auto& value = vertex.*p_member;
        write_bytes(p_output_file, value.data(), value.size() * sizeof(float), p_offset, p_output_path);
    }
    p_sections.append(make_geometry_section(p_slot, start, p_offset - start, "vec3"));
}

void write_vec2_section(std::ofstream& p_output_file,
    py::list& p_sections,
    const std::filesystem::path& p_output_path,
    size_t& p_offset,
    const std::vector<IntermediateVertex>& p_vertices,
    bool p_enabled)
{
    if (!p_enabled)
    {
        return;
    }
    const size_t start = p_offset;
    for (const IntermediateVertex& vertex : p_vertices)
    {
        write_bytes(p_output_file, vertex.uv.data(), vertex.uv.size() * sizeof(float), p_offset, p_output_path);
    }
    p_sections.append(make_geometry_section("uv", start, p_offset - start, "vec2"));
}

void write_index_section(std::ofstream& p_output_file,
    py::list& p_sections,
    const std::filesystem::path& p_output_path,
    size_t& p_offset,
    const IntermediateSubmesh& p_submesh)
{
    if (p_submesh.indices.size() % 3 != 0)
    {
        throw std::runtime_error("Model submesh index count is not a multiple of 3: " + p_submesh.id);
    }
    const size_t start = p_offset;
    for (unsigned int index : p_submesh.indices)
    {
        if (index >= p_submesh.vertices.size())
        {
            throw std::runtime_error("Model submesh index is out of range: " + p_submesh.id);
        }
        const uint32_t stored_index = static_cast<uint32_t>(index);
        write_bytes(p_output_file, &stored_index, sizeof(stored_index), p_offset, p_output_path);
    }
    p_sections.append(make_geometry_section("index", start, p_offset - start, "uint32"));
}

std::string geometry_path_for(const std::string& p_file_name, const std::string& p_geometry_path_prefix)
{
    if (p_geometry_path_prefix.empty())
    {
        return p_file_name;
    }
    return (std::filesystem::path(p_geometry_path_prefix) / p_file_name).generic_string();
}

py::list write_submesh_geometry(
    const IntermediateSubmesh& p_submesh, std::ofstream& p_output_file, const std::filesystem::path& p_output_path, size_t& p_offset)
{
    py::list sections;
    write_vec3_section(p_output_file, sections, p_output_path, p_offset, "position", p_submesh.vertices, &IntermediateVertex::position, true);
    write_vec3_section(p_output_file, sections, p_output_path, p_offset, "normal", p_submesh.vertices, &IntermediateVertex::normal, p_submesh.has_normal);
    write_vec3_section(
        p_output_file, sections, p_output_path, p_offset, "tangent", p_submesh.vertices, &IntermediateVertex::tangent, p_submesh.has_tangent_space);
    write_vec3_section(p_output_file,
        sections,
        p_output_path,
        p_offset,
        "bitangent",
        p_submesh.vertices,
        &IntermediateVertex::bitangent,
        p_submesh.has_tangent_space);
    write_vec2_section(p_output_file, sections, p_output_path, p_offset, p_submesh.vertices, p_submesh.has_uv);
    write_index_section(p_output_file, sections, p_output_path, p_offset, p_submesh);
    return sections;
}

py::dict to_python(const IntermediateSubmesh& p_submesh, const py::list& p_geometry_sections, const std::string& p_geometry_path)
{
    py::dict result;
    result["id"] = p_submesh.id;
    result["type"] = "submesh";
    result["geometry_sections"] = p_geometry_sections;
    result["geometry_path"] = p_geometry_path;
    result["material_id"] = p_submesh.has_material ? py::cast(p_submesh.material_id) : py::none();
    return result;
}

py::list submeshes_to_python(const IntermediateScene& p_scene,
    const std::string& p_mesh_id,
    const std::filesystem::path& p_geometry_output_dir,
    const std::string& p_geometry_path_prefix)
{
    std::filesystem::create_directories(p_geometry_output_dir);
    const std::string file_name = sanitize_file_stem(p_mesh_id) + ".geometry.bin";
    const std::filesystem::path output_path = p_geometry_output_dir / file_name;
    std::ofstream output_file(output_path, std::ios::binary);
    if (!output_file.is_open())
    {
        throw std::runtime_error("Failed to open model geometry binary for writing: " + output_path.generic_string());
    }

    const std::string geometry_path = geometry_path_for(file_name, p_geometry_path_prefix);
    size_t offset = 0;
    py::list result;
    for (const IntermediateSubmesh& submesh : p_scene.submeshes)
    {
        result.append(to_python(submesh, write_submesh_geometry(submesh, output_file, output_path, offset), geometry_path));
    }
    return result;
}

py::dict to_python(const IntermediateMaterialTexture& p_texture)
{
    py::dict texture;
    texture["type"] = "image";
    texture["file"] = p_texture.file;
    texture["color_space"] = p_texture.color_space;
    texture["channel_count"] = p_texture.channel_count;

    py::dict result;
    result["texture_key"] = p_texture.texture_key;
    result["texture"] = texture;
    return result;
}

py::dict material_to_python(const IntermediateMaterial& p_material,
    const py::list& p_graphics_pipeline_ids,
    const py::list& p_masked_graphics_pipeline_ids)
{
    py::dict result;
    result["id"] = p_material.id;
    result["type"] = "material";
    const py::list& graphics_pipeline_ids = p_material.masked && p_masked_graphics_pipeline_ids.size() > 0
                                                ? p_masked_graphics_pipeline_ids
                                                : p_graphics_pipeline_ids;
    result["graphics_pipeline_ids"] = pipeline_ids_from(graphics_pipeline_ids);

    py::list textures;
    for (const IntermediateMaterialTexture& texture : p_material.textures)
    {
        textures.append(to_python(texture));
    }
    result["textures"] = textures;
    return result;
}
}

py::dict ModelCompiler::compile_mesh(
    const std::filesystem::path& p_source_path,
    const std::string& p_resource_id,
    const py::list& p_graphics_pipeline_ids,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_geometry_output_dir,
    const std::string& p_geometry_path_prefix,
    float p_vertex_position_scale,
    const std::string& p_source_up_direction,
    const std::string& p_source_right_direction,
    const std::string& p_source_front_direction,
    const std::string& p_target_up_direction,
    const std::string& p_target_right_direction,
    const std::string& p_target_front_direction) const
{
    (void)p_graphics_pipeline_ids;
    const VertexTransform transform = make_vertex_transform(p_vertex_position_scale,
        p_source_up_direction,
        p_source_right_direction,
        p_source_front_direction,
        p_target_up_direction,
        p_target_right_direction,
        p_target_front_direction);
    const IntermediateScene scene = import_scene(p_source_path, p_resource_id, p_texture_output_dir, transform, {});

    py::dict result;
    const std::string mesh_id = p_resource_id + ".mesh";
    result["id"] = mesh_id;
    result["type"] = "mesh";
    result["submeshes"] = submeshes_to_python(scene, mesh_id, p_geometry_output_dir, p_geometry_path_prefix);
    return result;
}

py::list ModelCompiler::compile_materials(
    const std::filesystem::path& p_source_path,
    const std::string& p_resource_id,
    const py::list& p_graphics_pipeline_ids,
    const py::list& p_masked_graphics_pipeline_ids,
    const std::string& p_texture_output_dir,
    const std::filesystem::path& p_texture_output_root) const
{
    const IntermediateScene scene = import_scene(
        p_source_path,
        p_resource_id,
        p_texture_output_dir,
        make_vertex_transform(1.0F, "y", "x", "z", "y", "x", "z"),
        p_texture_output_root);

    py::list result;
    for (const IntermediateMaterial& material : scene.materials)
    {
        result.append(material_to_python(material, p_graphics_pipeline_ids, p_masked_graphics_pipeline_ids));
    }
    return result;
}
}
