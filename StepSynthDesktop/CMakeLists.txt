cmake_minimum_required(VERSION 3.20)
project(StepSynthDesktop C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# ---- Libraries downloaded automatically on the first build (needs git) ----
include(FetchContent)

# Dear ImGui: draws the buttons, sliders and grid.
FetchContent_Declare(imgui
    GIT_REPOSITORY https://github.com/ocornut/imgui.git
    GIT_TAG v1.91.9b
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR do-not-build  # only download it; we compile the files we need below
)

# miniaudio: sends sound to your speakers (works with PipeWire, PulseAudio and ALSA).
FetchContent_Declare(miniaudio
    GIT_REPOSITORY https://github.com/mackron/miniaudio.git
    GIT_TAG 0.11.25
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR do-not-build
)

FetchContent_MakeAvailable(imgui miniaudio)

# ---- Libraries installed with apt (see README) ----
find_package(SDL2 REQUIRED CONFIG)  # the window, mouse and keyboard
find_package(Threads REQUIRED)

add_library(imgui STATIC
    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdl2.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdlrenderer2.cpp
)
target_include_directories(imgui PUBLIC ${imgui_SOURCE_DIR} ${imgui_SOURCE_DIR}/backends)
target_link_libraries(imgui PUBLIC SDL2::SDL2)

add_library(miniaudio STATIC ${miniaudio_SOURCE_DIR}/miniaudio.c)
target_include_directories(miniaudio PUBLIC ${miniaudio_SOURCE_DIR})
target_link_libraries(miniaudio PUBLIC Threads::Threads m ${CMAKE_DL_LIBS})

# ---- The app ----
# The audio engine is shared with the Android app: same files, same sound.
set(ENGINE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../StepSynth/app/src/main/cpp/engine)

add_executable(stepsynth
    src/main.cpp
    src/AudioOutput.cpp
    src/StepSynthUi.cpp
    ${ENGINE_DIR}/AudioEngine.cpp
)
target_include_directories(stepsynth PRIVATE ${ENGINE_DIR})
target_compile_options(stepsynth PRIVATE -Wall -Wextra)
target_link_libraries(stepsynth PRIVATE imgui miniaudio)
