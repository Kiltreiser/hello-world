// StepSynth for Linux: opens a window, starts the audio, and redraws the
// screen about 60 times a second until you close it.
#include <SDL.h>
#include <imgui.h>
#include <imgui_impl_sdl2.h>
#include <imgui_impl_sdlrenderer2.h>

#include <cstdio>

#include "AudioEngine.h"
#include "AudioOutput.h"
#include "StepSynthUi.h"

namespace {

void setUpLookAndFeel() {
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;  // don't write an imgui.ini file next to the app

    // Use a clean system font if one is installed (Mint has DejaVu Sans), else ImGui's built-in one.
    const char* fontPath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
    if (FILE* f = std::fopen(fontPath, "rb")) {
        std::fclose(f);
        io.Fonts->AddFontFromFileTTF(fontPath, 17.0f);
    } else {
        ImFontConfig config;
        config.SizePixels = 17.0f;
        io.Fonts->AddFontDefault(&config);
    }

    ImGui::StyleColorsDark();
    ImGuiStyle& style = ImGui::GetStyle();
    style.WindowPadding = ImVec2(20, 16);
    style.FrameRounding = 6.0f;
    style.GrabRounding = 6.0f;
    style.FramePadding = ImVec2(10, 6);
    style.ItemSpacing = ImVec2(8, 8);
    style.Colors[ImGuiCol_WindowBg] = ImVec4(0.08f, 0.08f, 0.08f, 1.0f);
    style.Colors[ImGuiCol_FrameBg] = ImVec4(0.18f, 0.18f, 0.18f, 1.0f);
    style.Colors[ImGuiCol_FrameBgHovered] = ImVec4(0.24f, 0.24f, 0.24f, 1.0f);
    style.Colors[ImGuiCol_FrameBgActive] = ImVec4(0.28f, 0.28f, 0.28f, 1.0f);
    style.Colors[ImGuiCol_SliderGrab] = ImVec4(1.00f, 0.48f, 0.10f, 1.0f);
    style.Colors[ImGuiCol_SliderGrabActive] = ImVec4(1.00f, 0.60f, 0.30f, 1.0f);
    style.Colors[ImGuiCol_CheckMark] = ImVec4(1.00f, 0.48f, 0.10f, 1.0f);
    style.Colors[ImGuiCol_Button] = ImVec4(0.22f, 0.22f, 0.22f, 1.0f);
    style.Colors[ImGuiCol_ButtonHovered] = ImVec4(0.30f, 0.30f, 0.30f, 1.0f);
    style.Colors[ImGuiCol_ButtonActive] = ImVec4(0.38f, 0.38f, 0.38f, 1.0f);
}

}  // namespace

int main(int, char**) {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        std::fprintf(stderr, "Could not start SDL: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window* window = SDL_CreateWindow("StepSynth", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1180, 760,
                                          SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if (!window) {
        std::fprintf(stderr, "Could not create window: %s\n", SDL_GetError());
        return 1;
    }
    SDL_SetWindowMinimumSize(window, 900, 640);

    // Prefer the graphics card with vsync; fall back to software drawing if needed.
    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer) {
        std::fprintf(stderr, "Could not create renderer: %s\n", SDL_GetError());
        return 1;
    }

    ImGui::CreateContext();
    setUpLookAndFeel();
    ImGui_ImplSDL2_InitForSDLRenderer(window, renderer);
    ImGui_ImplSDLRenderer2_Init(renderer);

    {
        // The engine is created before the audio output and destroyed after it,
        // so the audio thread never uses an engine that no longer exists.
        AudioEngine engine;
        StepSynthUi ui(engine);
        AudioOutput audio(engine);
        audio.start();
        const std::string audioStatus = audio.description();
        const bool audioOk = audio.isAudible();

        bool running = true;
        while (running) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                ImGui_ImplSDL2_ProcessEvent(&event);
                if (event.type == SDL_QUIT) running = false;
            }
            if (SDL_GetWindowFlags(window) & SDL_WINDOW_MINIMIZED) {
                SDL_Delay(20);  // nothing to draw; the music keeps playing
                continue;
            }

            ImGui_ImplSDLRenderer2_NewFrame();
            ImGui_ImplSDL2_NewFrame();
            ImGui::NewFrame();
            ui.draw(audioStatus, audioOk);
            ImGui::Render();

            const ImGuiIO& io = ImGui::GetIO();
            SDL_RenderSetScale(renderer, io.DisplayFramebufferScale.x, io.DisplayFramebufferScale.y);
            SDL_SetRenderDrawColor(renderer, 20, 20, 20, 255);
            SDL_RenderClear(renderer);
            ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData(), renderer);
            SDL_RenderPresent(renderer);
        }
    }

    ImGui_ImplSDLRenderer2_Shutdown();
    ImGui_ImplSDL2_Shutdown();
    ImGui::DestroyContext();
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
