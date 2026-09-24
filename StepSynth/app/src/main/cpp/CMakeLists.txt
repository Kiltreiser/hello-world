cmake_minimum_required(VERSION 3.22.1)
project(stepsynth CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Oboe comes from the Gradle dependency com.google.oboe:oboe (via "prefab").
find_package(oboe REQUIRED CONFIG)

add_library(stepsynth SHARED
    jni_bridge.cpp
    OboePlayer.cpp
    engine/AudioEngine.cpp
)

target_compile_options(stepsynth PRIVATE -Wall -Wextra -O2)

target_link_libraries(stepsynth
    oboe::oboe
    android
    log
)
