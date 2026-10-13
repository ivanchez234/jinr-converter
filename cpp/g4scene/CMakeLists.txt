# Отдельная сборка g4scene — только чтобы гонять её тесты при разработке.
# В сгенерированные проекты библиотека копируется исходниками и собирается
# вместе с ними, этот файл там не нужен.
#
#   source $HOME/geant4/install/bin/geant4.sh      # или g4env
#   cmake -S cpp/g4scene -B build/g4scene
#   cmake --build build/g4scene -j$(nproc)
#   ctest --test-dir build/g4scene --output-on-failure

cmake_minimum_required(VERSION 3.16)
project(g4scene CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

find_package(Geant4 REQUIRED)
include(${Geant4_USE_FILE})

add_library(g4scene STATIC
  src/Transform.cc
  src/Registry.cc
  src/Materials.cc)
target_include_directories(g4scene PUBLIC include)
target_link_libraries(g4scene PUBLIC ${Geant4_LIBRARIES})
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(g4scene PRIVATE -Wall -Wextra)
endif()

enable_testing()
add_executable(test_g4scene tests/test_g4scene.cc)
target_link_libraries(test_g4scene PRIVATE g4scene)
add_test(NAME g4scene COMMAND test_g4scene)
