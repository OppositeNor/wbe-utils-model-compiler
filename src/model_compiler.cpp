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
#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <assimp/Importer.hpp>
#include <assimp/material.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <pybind11/pybind11.h>

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
    std::vector<std::pair<int, float>> bones;
};

struct IntermediateSubmesh
{
    std::string id;
    std::vector<IntermediateVertex> vertices;
    std::vector<unsigned int> indices;
    std::string material_id;
    bool has_material = false;
};

struct IntermediateMaterialTexture
{
    std::string texture_key;
    std::string path;
    std::string color_space;
    int channel_count = 4;
};

struct IntermediateMaterial
{
    std::string id;
    std::vector<IntermediateMaterialTexture> textures;
};

struct IntermediateScene
{
    std::vector<IntermediateSubmesh> submeshes;
    std::vector<IntermediateMaterial> materials;
};

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

std::string material_id_for(const aiMaterial* p_material, const std::string& p_resource_id, unsigned int p_material_index)
{
    aiString material_name;
    if (p_material != nullptr && p_material->Get(AI_MATKEY_NAME, material_name) == AI_SUCCESS && material_name.length > 0)
    {
        return material_name.C_Str();
    }
    return p_resource_id + "_material_" + std::to_string(p_material_index);
}

std::string submesh_id_for(const aiMesh* p_mesh, const std::string& p_resource_id, unsigned int p_mesh_index)
{
    if (p_mesh->mName.length > 0)
    {
        return p_mesh->mName.C_Str();
    }
    return p_resource_id + "_submesh_" + std::to_string(p_mesh_index);
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

bool add_texture(
    const aiMaterial* p_material,
    aiTextureType p_texture_type,
    const std::string& p_texture_key,
    const std::string& p_color_space,
    int p_channel_count,
    const std::string& p_texture_output_dir,
    std::vector<IntermediateMaterialTexture>& p_textures)
{
    aiString texture_path;
    if (p_material->GetTexture(p_texture_type, 0, &texture_path) != AI_SUCCESS || texture_path.length == 0)
    {
        return false;
    }

    p_textures.push_back(IntermediateMaterialTexture{
        .texture_key = p_texture_key,
        .path = texture_output_path(texture_path, p_texture_output_dir),
        .color_space = p_color_space,
        .channel_count = p_channel_count,
    });
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

IntermediateSubmesh import_submesh(const aiScene* p_scene, const aiMesh* p_mesh, const std::string& p_resource_id, unsigned int p_mesh_index)
{
    IntermediateSubmesh result;
    result.id = submesh_id_for(p_mesh, p_resource_id, p_mesh_index);
    result.vertices.reserve(p_mesh->mNumVertices);
    result.indices.reserve(p_mesh->mNumFaces * 3);

    if (p_mesh->mMaterialIndex < p_scene->mNumMaterials)
    {
        result.has_material = true;
        result.material_id = material_id_for(p_scene->mMaterials[p_mesh->mMaterialIndex], p_resource_id, p_mesh->mMaterialIndex);
    }

    for (unsigned int vertex_index = 0; vertex_index < p_mesh->mNumVertices; ++vertex_index)
    {
        IntermediateVertex vertex;
        const aiVector3D& position = p_mesh->mVertices[vertex_index];
        vertex.position = {position.x, position.y, position.z};

        if (p_mesh->HasTextureCoords(0))
        {
            const aiVector3D& uv = p_mesh->mTextureCoords[0][vertex_index];
            vertex.uv = {uv.x, uv.y};
        }

        if (p_mesh->HasNormals())
        {
            const aiVector3D& normal = p_mesh->mNormals[vertex_index];
            vertex.normal = {normal.x, normal.y, normal.z};
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

    return result;
}

IntermediateMaterial import_material(
    const aiMaterial* p_material,
    const std::string& p_resource_id,
    unsigned int p_material_index,
    const std::string& p_texture_output_dir)
{
    IntermediateMaterial result;
    result.id = material_id_for(p_material, p_resource_id, p_material_index);

    if (!add_texture(p_material, aiTextureType_BASE_COLOR, "base_color", "srgb", 4, p_texture_output_dir, result.textures))
    {
        add_texture(p_material, aiTextureType_DIFFUSE, "base_color", "srgb", 4, p_texture_output_dir, result.textures);
    }

    if (!add_texture(p_material, aiTextureType_METALNESS, "roughness_metallic_ao", "linear", 3, p_texture_output_dir, result.textures) &&
        !add_texture(p_material, aiTextureType_DIFFUSE_ROUGHNESS, "roughness_metallic_ao", "linear", 3, p_texture_output_dir, result.textures))
    {
        add_texture(p_material, aiTextureType_AMBIENT_OCCLUSION, "roughness_metallic_ao", "linear", 3, p_texture_output_dir, result.textures);
    }

    return result;
}

IntermediateScene import_scene(const std::filesystem::path& p_source_path, const std::string& p_resource_id, const std::string& p_texture_output_dir)
{
    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        p_source_path.string(),
        aiProcess_Triangulate | aiProcess_GenNormals | aiProcess_JoinIdenticalVertices | aiProcess_ImproveCacheLocality);
    if (scene == nullptr)
    {
        throw std::runtime_error("Assimp failed to load mesh asset: " + std::string(importer.GetErrorString()));
    }

    IntermediateScene result;
    result.submeshes.reserve(scene->mNumMeshes);
    result.materials.reserve(scene->mNumMaterials);

    for (unsigned int material_index = 0; material_index < scene->mNumMaterials; ++material_index)
    {
        result.materials.push_back(import_material(scene->mMaterials[material_index], p_resource_id, material_index, p_texture_output_dir));
    }

    for (unsigned int mesh_index = 0; mesh_index < scene->mNumMeshes; ++mesh_index)
    {
        result.submeshes.push_back(import_submesh(scene, scene->mMeshes[mesh_index], p_resource_id, mesh_index));
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

py::dict to_python(const IntermediateVertex& p_vertex)
{
    py::dict result;
    result["position"] = make_vec3(p_vertex.position);
    result["uv"] = make_uv(p_vertex.uv);
    result["normal"] = make_vec3(p_vertex.normal);
    result["bones"] = make_bones(p_vertex.bones);
    return result;
}

py::dict to_python(const IntermediateSubmesh& p_submesh)
{
    py::dict result;
    result["id"] = p_submesh.id;
    result["type"] = "submesh";

    py::list vertices;
    for (const IntermediateVertex& vertex : p_submesh.vertices)
    {
        vertices.append(to_python(vertex));
    }
    result["vertices_data"] = vertices;

    py::list indices;
    for (unsigned int index : p_submesh.indices)
    {
        indices.append(index);
    }
    result["indices_data"] = indices;
    result["material_id"] = p_submesh.has_material ? py::cast(p_submesh.material_id) : py::none();
    return result;
}

py::dict to_python(const IntermediateMaterialTexture& p_texture)
{
    py::dict texture;
    texture["type"] = "image";
    texture["file"] = p_texture.path;
    texture["color_space"] = p_texture.color_space;
    texture["channel_count"] = p_texture.channel_count;

    py::dict result;
    result["texture_key"] = p_texture.texture_key;
    result["texture"] = texture;
    return result;
}

py::dict material_to_python(const IntermediateMaterial& p_material, const py::list& p_graphics_pipeline_ids)
{
    py::dict result;
    result["id"] = p_material.id;
    result["type"] = "material";
    result["graphics_pipeline_ids"] = pipeline_ids_from(p_graphics_pipeline_ids);

    py::list textures;
    for (const IntermediateMaterialTexture& texture : p_material.textures)
    {
        textures.append(to_python(texture));
    }
    result["textures"] = textures;
    return result;
}
}

py::dict MeshCompiler::compile_mesh(
    const std::filesystem::path& p_source_path,
    const std::string& p_resource_id,
    const py::list& p_graphics_pipeline_ids,
    const std::string& p_texture_output_dir) const
{
    (void)p_graphics_pipeline_ids;
    const IntermediateScene scene = import_scene(p_source_path, p_resource_id, p_texture_output_dir);

    py::dict result;
    result["id"] = p_resource_id;
    result["type"] = "mesh";

    py::list submeshes;
    for (const IntermediateSubmesh& submesh : scene.submeshes)
    {
        submeshes.append(to_python(submesh));
    }
    result["submeshes"] = submeshes;
    return result;
}

py::list MeshCompiler::compile_materials(
    const std::filesystem::path& p_source_path,
    const std::string& p_resource_id,
    const py::list& p_graphics_pipeline_ids,
    const std::string& p_texture_output_dir) const
{
    const IntermediateScene scene = import_scene(p_source_path, p_resource_id, p_texture_output_dir);

    py::list result;
    for (const IntermediateMaterial& material : scene.materials)
    {
        result.append(material_to_python(material, p_graphics_pipeline_ids));
    }
    return result;
}
}
