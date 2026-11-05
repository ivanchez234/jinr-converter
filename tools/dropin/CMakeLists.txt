# Проверка «сцена в чужом проекте» (tools/e2e.sh, часть 5).
#
# Одна программа, как у физика: свой DetectorConstruction с самым обычным именем и две
# сгенерированные сцены рядом. Объектные файлы обеих сцен линкуются в одну программу,
# поэтому, если у сцен одинаковые имена классов, сборка упадёт (multiple definition),
# а если класс физика столкнётся с нашим — упадёт компиляция.
#
#   cmake -S tools/dropin -B <папка сборки> -DSCENE_A=<проект A> -DSCENE_B=<проект B> \
#         -DNS_A=<namespace A> -DNS_B=<namespace B>
#   cmake --build <папка сборки> && <папка сборки>/dropin
#
# SCENE_A и SCENE_B — абсолютные пути к проектам из mcscene generate.

cmake_minimum_required(VERSION 3.16)
project(mcscene_dropin CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

foreach(v SCENE_A SCENE_B NS_A NS_B)
  if(NOT ${v})
    message(FATAL_ERROR "нужно задать -D${v}=...")
  endif()
endforeach()

find_package(Geant4 REQUIRED)
include(${Geant4_USE_FILE})

# g4scene одна на всю программу: у обеих сцен лежит одинаковая копия.
# Geant4 11 отдаёт пути к своим заголовкам вместе с библиотеками (${Geant4_LIBRARIES}),
# поэтому всё, что включает заголовки Geant4, связывается с g4scene_once (PUBLIC — дальше).
file(GLOB G4SCENE_SRC ${SCENE_A}/g4scene/src/*.cc)
add_library(g4scene_once STATIC ${G4SCENE_SRC})
target_include_directories(g4scene_once PUBLIC ${SCENE_A}/g4scene/include)
target_link_libraries(g4scene_once PUBLIC ${Geant4_LIBRARIES})

# Геометрия каждой сцены — объектные файлы, у каждой свои include.
foreach(S A B)
  file(GLOB SCENE_SRC_${S} ${SCENE_${S}}/generated/*.cc)
  add_library(scene_${S} OBJECT ${SCENE_SRC_${S}})
  target_include_directories(scene_${S} PRIVATE ${SCENE_${S}}/generated ${SCENE_${S}}/user)
  target_link_libraries(scene_${S} PRIVATE g4scene_once)
endforeach()

# Вторая сцена создаётся в своём файле: файлы у всех сцен называются одинаково
# (DetectorConstruction.hh), поэтому один .cc видит заголовки только одной сцены.
add_library(make_second OBJECT make_second.cc)
target_include_directories(make_second PRIVATE ${SCENE_B}/generated ${SCENE_B}/user)
target_link_libraries(make_second PRIVATE g4scene_once)
target_compile_definitions(make_second PRIVATE NS_B=${NS_B})

add_executable(dropin physicist_main.cc
               $<TARGET_OBJECTS:scene_A> $<TARGET_OBJECTS:scene_B> $<TARGET_OBJECTS:make_second>)
target_include_directories(dropin PRIVATE ${SCENE_A}/generated ${SCENE_A}/user)
target_compile_definitions(dropin PRIVATE NS_A=${NS_A})
target_link_libraries(dropin PRIVATE g4scene_once)
