cmake_minimum_required(VERSION 3.19)
find_package(ASC REQUIRED)
project(native_eval_smoke LANGUAGES ASC CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(NPU_ARCH "dav-2201" CACHE STRING "Explicit target compiler architecture")
find_package(Python3 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import torch; print(torch.utils.cmake_prefix_path)"
                OUTPUT_VARIABLE TORCH_PREFIX OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
find_package(Torch REQUIRED HINTS ${TORCH_PREFIX})
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import pathlib,torch_npu; print(pathlib.Path(torch_npu.__file__).parent)"
                OUTPUT_VARIABLE TORCH_NPU_DIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND uname -m OUTPUT_VARIABLE HOST_ARCH OUTPUT_STRIP_TRAILING_WHITESPACE)
add_library(native_eval_smoke SHARED kernels.asc extension.cpp)
target_include_directories(native_eval_smoke PRIVATE ${TORCH_INCLUDE_DIRS} "${TORCH_NPU_DIR}/include"
                           "$ENV{ASCEND_HOME_PATH}/include" "$ENV{ASCEND_HOME_PATH}/${HOST_ARCH}-linux/include")
target_link_directories(native_eval_smoke PRIVATE "${TORCH_NPU_DIR}/lib"
                        "$ENV{ASCEND_HOME_PATH}/lib64" "$ENV{ASCEND_HOME_PATH}/${HOST_ARCH}-linux/lib64")
target_link_libraries(native_eval_smoke PRIVATE ${TORCH_LIBRARIES} torch_npu ascendcl ascendc_runtime)
separate_arguments(TORCH_FLAGS NATIVE_COMMAND "${TORCH_CXX_FLAGS}")
target_compile_options(native_eval_smoke PRIVATE ${TORCH_FLAGS} $<$<COMPILE_LANGUAGE:ASC>:--npu-arch=${NPU_ARCH}>)
if(NATIVE_WRONG)
    target_compile_definitions(native_eval_smoke PRIVATE NATIVE_WRONG)
endif()
