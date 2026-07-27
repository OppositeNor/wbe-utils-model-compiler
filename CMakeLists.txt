# Copyright 2025 OppositeNor
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
cmake_minimum_required(VERSION 3.22)

project(wbe_build_utils_mesh_compiler LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

execute_process(
    COMMAND "${Python3_EXECUTABLE}" -m pybind11 --cmakedir
    OUTPUT_VARIABLE WBE_PYBIND11_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE WBE_PYBIND11_RESULT
)
if(NOT WBE_PYBIND11_RESULT EQUAL 0)
    message(FATAL_ERROR "pybind11 is required. Install dependencies from requirements.txt before configuring.")
endif()
set(pybind11_DIR "${WBE_PYBIND11_CMAKE_DIR}" CACHE PATH "pybind11 CMake package directory")
find_package(pybind11 CONFIG REQUIRED)

set(WBE_ASSIMP_ROOT "${CMAKE_CURRENT_LIST_DIR}/../dependencies/assimp" CACHE PATH "Path to Assimp source directory")
if(NOT EXISTS "${WBE_ASSIMP_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR "Assimp source was not found at '${WBE_ASSIMP_ROOT}'. Set WBE_ASSIMP_ROOT or pass -DWBE_ASSIMP_ROOT=...")
endif()
set(ASSIMP_BUILD_ASSIMP_TOOLS OFF CACHE BOOL "" FORCE)
set(ASSIMP_BUILD_SAMPLES OFF CACHE BOOL "" FORCE)
set(ASSIMP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(ASSIMP_BUILD_ZLIB ON CACHE BOOL "" FORCE)
set(ASSIMP_WARNINGS_AS_ERRORS OFF CACHE BOOL "" FORCE)
set(ASSIMP_INSTALL OFF CACHE BOOL "" FORCE)
set(ASSIMP_NO_EXPORT ON CACHE BOOL "" FORCE)
add_subdirectory("${WBE_ASSIMP_ROOT}" "${CMAKE_BINARY_DIR}/assimp")
if(TARGET assimp::assimp)
    set(WBE_ASSIMP_TARGET assimp::assimp)
else()
    set(WBE_ASSIMP_TARGET assimp)
endif()

if(NOT DEFINED PYTHON_EXTENSION_OUTPUT_DIRECTORY)
    set(PYTHON_EXTENSION_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/wbe_build_utils_mesh_compiler")
endif()

pybind11_add_module(_native
    src/mesh_compiler.cpp
    src/python_module.cpp
)

target_include_directories(_native PRIVATE include)
target_link_libraries(_native PRIVATE ${WBE_ASSIMP_TARGET})

set_target_properties(_native PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${PYTHON_EXTENSION_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${PYTHON_EXTENSION_OUTPUT_DIRECTORY}"
)
