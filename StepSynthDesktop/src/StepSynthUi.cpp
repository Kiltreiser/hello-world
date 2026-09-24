#include "StepSynthUi.h"

#define IMGUI_DEFINE_MATH_OPERATORS
#include <imgui.h>

#include <algorithm>
#include <cstdio>

namespace {

const char* kTrackNames[] = {"Kick", "Snare", "Hat", "Clap", "Synth"};
const char* kNoteNames[] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};

constexpr int kSynthRow = 4;

// Same colors as the Android app: kick, snare, hat, clap, synth.
const ImVec4 kTrackColors[] = {
    ImVec4(1.00f, 0.48f, 0.10f, 1.0f),
    ImVec4(1.00f, 0.76f, 0.10f, 1.0f),
    ImVec4(0.18f, 0.77f, 0.91f, 1.0f),
    ImVec4(1.00f, 0.36f, 0.60f, 1.0f),
    ImVec4(0.49f, 0.85f, 0.34f, 1.0f),
};
const ImVec4 kCellOff(0.14f, 0.14f, 0.14f, 1.0f);
const ImVec4 kTextDark(0.08f, 0.08f, 0.08f, 1.0f);
const ImVec4 kTextDim(0.55f, 0.55f, 0.55f, 1.0f);

// Computer keys laid out like a piano: the middle letter row is the white
// keys, the row above is the black keys.
const ImGuiKey kPianoComputerKeys[] = {
    ImGuiKey_A, ImGuiKey_W, ImGuiKey_S, ImGuiKey_E, ImGuiKey_D, ImGuiKey_F, ImGuiKey_T,
    ImGuiKey_G, ImGuiKey_Y, ImGuiKey_H, ImGuiKey_U, ImGuiKey_J, ImGuiKey_K,
};
const char* kPianoComputerKeyNames[] = {"A", "W", "S", "E", "D", "F", "T", "G", "Y", "H", "U", "J", "K"};

std::string noteName(int note) {
    return std::string(kNoteNames[note % 12]) + std::to_string(note / 12 - 1);
}

bool isBlackKey(int note) {
    return kNoteNames[note % 12][1] == '#';
}

ImVec4 brighter(ImVec4 c, float amount) {
    return ImVec4(std::min(c.x + amount, 1.0f), std::min(c.y + amount, 1.0f), std::min(c.z + amount, 1.0f), c.w);
}

ImVec4 dimmed(ImVec4 c) {
    return ImVec4(c.x * 0.4f, c.y * 0.4f, c.z * 0.4f, c.w);
}

// A button in a solid color, with lighter shades for hover and click.
bool ColoredButton(const char* label, ImVec4 color, ImVec4 textColor, ImVec2 size) {
    ImGui::PushStyleColor(ImGuiCol_Button, color);
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, brighter(color, 0.08f));
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, brighter(color, 0.18f));
    ImGui::PushStyleColor(ImGuiCol_Text, textColor);
    bool clicked = ImGui::Button(label, size);
    ImGui::PopStyleColor(4);
    return clicked;
}

// A slider that shows 0..100 but stores 0..1.
bool PercentSlider(const char* label, float* value) {
    float shown = *value * 100.0f;
    if (ImGui::SliderFloat(label, &shown, 0.0f, 100.0f, "%.0f")) {
        *value = shown / 100.0f;
        return true;
    }
    return false;
}

}  // namespace

StepSynthUi::StepSynthUi(AudioEngine& engine) : mEngine(engine) {
    mSynthSteps.fill(kNoNote);
    mMouseHeld.fill(kNoNote);
    mKeyboardHeld.fill(kNoNote);
    loadDemoPattern();
    sendEverythingToEngine();
}

void StepSynthUi::draw(const std::string& audioStatus, bool audioOk) {
    handleComputerKeyboard();

    // One window that fills the whole app window, with no title bar.
    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(viewport->WorkPos);
    ImGui::SetNextWindowSize(viewport->WorkSize);
    ImGui::Begin("StepSynth", nullptr,
                 ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_NoBringToFrontOnFocus | ImGuiWindowFlags_NoScrollWithMouse);

    drawTransport();
    ImGui::Spacing();
    drawPatternGrid();
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    drawDrumPads();
    ImGui::Spacing();
    drawKeyboard();
    ImGui::Spacing();
    drawSynthControls();
    drawStatusBar(audioStatus, audioOk);

    ImGui::End();
}

void StepSynthUi::drawTransport() {
    ImGui::SetWindowFontScale(1.5f);
    ImGui::TextUnformatted("StepSynth");
    ImGui::SetWindowFontScale(1.0f);

    ImGui::SameLine(0.0f, 32.0f);
    ImVec4 playColor = mPlaying ? kTrackColors[0] : ImVec4(0.25f, 0.25f, 0.25f, 1.0f);
    if (ColoredButton(mPlaying ? "Stop  (Space)" : "Play  (Space)", playColor,
                      mPlaying ? kTextDark : ImVec4(1, 1, 1, 1), ImVec2(150, 0))) {
        togglePlaying();
    }

    ImGui::SameLine(0.0f, 32.0f);
    ImGui::SetNextItemWidth(220);
    if (ImGui::SliderFloat("Tempo", &mTempo, 60.0f, 200.0f, "%.0f BPM")) {
        mTempo = static_cast<float>(static_cast<int>(mTempo + 0.5f));
        mEngine.setTempo(mTempo);
    }

    ImGui::SameLine(0.0f, 32.0f);
    ImGui::SetNextItemWidth(160);
    if (ImGui::SliderInt("Swing", &mSwingPercent, 50, 75, "%d%%")) {
        mEngine.setSwing((mSwingPercent - 50) / 50.0f);
    }
}

// Five rows (one per track) of 16 steps. Click a cell to turn it on or off.
void StepSynthUi::drawPatternGrid() {
    const float nameWidth = 90.0f;
    const float gap = 4.0f;
    const float beatGap = 14.0f;  // extra space between each group of 4 steps
    float available = ImGui::GetContentRegionAvail().x - nameWidth - gap;
    float cell = (available - gap * 12 - beatGap * 3) / kSteps;
    cell = std::clamp(cell, 24.0f, 54.0f);

    const int playhead = mEngine.currentStep();
    ImDrawList* drawList = ImGui::GetWindowDrawList();
    ImGuiIO& io = ImGui::GetIO();

    for (int track = 0; track < 5; ++track) {
        ImGui::PushID(track);
        const ImVec4 color = kTrackColors[track];

        // Track name. Drum names can be clicked to hear the sound.
        ColoredButton(kTrackNames[track], dimmed(color), ImVec4(1, 1, 1, 1), ImVec2(nameWidth, cell));
        if (track < kDrumTracks && ImGui::IsItemActivated()) mEngine.triggerDrum(track);
        if (track == kSynthRow && ImGui::IsItemHovered()) {
            ImGui::SetTooltip("Scroll the mouse wheel over a synth step to change its note");
        }

        for (int step = 0; step < kSteps; ++step) {
            ImGui::SameLine(0.0f, step == 0 ? gap : (step % 4 == 0 ? beatGap : gap));
            ImGui::PushID(step);

            const bool on = track == kSynthRow ? mSynthSteps[step] != kNoNote : mDrumSteps[track][step];
            std::string label = (track == kSynthRow && on) ? noteName(mSynthSteps[step]) : "";
            label += "##cell";
            // Beat starts (steps 1, 5, 9, 13) are slightly lighter to help you count.
            ImVec4 offColor = (step % 4 == 0) ? brighter(kCellOff, 0.05f) : kCellOff;

            if (ColoredButton(label.c_str(), on ? color : offColor, kTextDark, ImVec2(cell, cell))) {
                if (track == kSynthRow) {
                    setSynthStep(step, on ? kNoNote : mLastNote);
                } else {
                    setDrumStep(track, step, !on);
                }
            }

            // Mouse wheel over a synth step moves its note up or down.
            if (track == kSynthRow && on && ImGui::IsItemHovered() && io.MouseWheel != 0.0f) {
                int note = std::clamp(mSynthSteps[step] + (io.MouseWheel > 0 ? 1 : -1), 24, 96);
                setSynthStep(step, note);
                mLastNote = note;
            }

            if (step == playhead) {
                drawList->AddRect(ImGui::GetItemRectMin() - ImVec2(2, 2), ImGui::GetItemRectMax() + ImVec2(2, 2),
                                  IM_COL32(255, 255, 255, 230), 6.0f, 0, 2.5f);
            }
            ImGui::PopID();
        }
        ImGui::PopID();
    }
}

void StepSynthUi::drawDrumPads() {
    ImGui::TextColored(kTextDim, "Drum pads  (keys 1-4)");
    const float width = std::min((ImGui::GetContentRegionAvail().x - 3 * 8.0f) / 4, 160.0f);
    for (int track = 0; track < kDrumTracks; ++track) {
        if (track > 0) ImGui::SameLine(0.0f, 8.0f);
        ColoredButton(kTrackNames[track], dimmed(kTrackColors[track]), ImVec4(1, 1, 1, 1), ImVec2(width, 56));
        // Sound on mouse-down, like a real pad, not on release like a normal button.
        if (ImGui::IsItemActivated()) mEngine.triggerDrum(track);
    }
}

void StepSynthUi::drawKeyboard() {
    ImGui::TextColored(kTextDim, "Keys %s-%s", noteName(lowestKey()).c_str(), noteName(lowestKey() + 12).c_str());
    ImGui::SameLine(0.0f, 16.0f);
    if (ImGui::SmallButton("Octave -  (Z)")) mOctave = std::max(mOctave - 1, 1);
    ImGui::SameLine();
    if (ImGui::SmallButton("Octave +  (X)")) mOctave = std::min(mOctave + 1, 6);

    const ImVec4 green = kTrackColors[kSynthRow];
    const float keyWidth = std::min((ImGui::GetContentRegionAvail().x - 12 * 3.0f) / kPianoKeys, 56.0f);
    const float top = ImGui::GetCursorPosY();

    for (int i = 0; i < kPianoKeys; ++i) {
        const int note = lowestKey() + i;
        const bool black = isBlackKey(note);
        const bool held = mMouseHeld[i] != kNoNote || mKeyboardHeld[i] != kNoNote;

        if (i > 0) ImGui::SameLine(0.0f, 3.0f);
        ImGui::SetCursorPosY(top);
        ImVec4 color = black ? ImVec4(0.18f, 0.30f, 0.14f, 1.0f) : ImVec4(0.26f, 0.44f, 0.20f, 1.0f);
        char label[32];
        std::snprintf(label, sizeof(label), "%s\n\n%s##key%d", kNoteNames[note % 12], kPianoComputerKeyNames[i], i);
        ColoredButton(label, held ? green : color, ImVec4(1, 1, 1, 1), ImVec2(keyWidth, black ? 70.0f : 104.0f));

        if (ImGui::IsItemActivated()) {
            mMouseHeld[i] = note;
            noteOn(note);
        }
        if (ImGui::IsItemDeactivated() && mMouseHeld[i] != kNoNote) {
            noteOff(mMouseHeld[i]);
            mMouseHeld[i] = kNoNote;
        }
    }
}

void StepSynthUi::drawSynthControls() {
    ImGui::TextColored(kTextDim, "Synth");
    ImGui::SameLine(0.0f, 16.0f);
    bool square = mSynthParams[kParamWaveform] >= 0.5f;
    if (ImGui::RadioButton("Saw", !square)) setSynthParam(kParamWaveform, 0.0f);
    ImGui::SameLine();
    if (ImGui::RadioButton("Square", square)) setSynthParam(kParamWaveform, 1.0f);

    struct Control {
        const char* label;
        int param;
    };
    const Control controls[] = {
        {"Cutoff", kParamCutoff},
        {"Resonance", kParamResonance},
        {"Env depth", kParamEnvAmount},
        {"Decay", kParamDecay},
    };
    const float width = std::min((ImGui::GetContentRegionAvail().x - 3 * 110.0f) / 4, 200.0f);
    for (int i = 0; i < 4; ++i) {
        if (i > 0) ImGui::SameLine(0.0f, 24.0f);
        ImGui::SetNextItemWidth(width);
        float value = mSynthParams[controls[i].param];
        if (PercentSlider(controls[i].label, &value)) setSynthParam(controls[i].param, value);
    }
}

void StepSynthUi::drawStatusBar(const std::string& audioStatus, bool audioOk) {
    const float lineHeight = ImGui::GetTextLineHeightWithSpacing();
    const float bottom = ImGui::GetWindowHeight() - ImGui::GetStyle().WindowPadding.y - lineHeight * 2;
    if (ImGui::GetCursorPosY() < bottom) ImGui::SetCursorPosY(bottom);
    ImGui::Separator();
    if (audioOk) {
        ImGui::TextColored(kTextDim, "Audio: %s", audioStatus.c_str());
        ImGui::SameLine(0.0f, 24.0f);
        ImGui::TextColored(kTextDim, "Click a key, then click a Synth step to place that note.");
    } else {
        ImGui::TextColored(ImVec4(1.0f, 0.4f, 0.4f, 1.0f), "Audio problem: %s", audioStatus.c_str());
    }
}

void StepSynthUi::handleComputerKeyboard() {
    // Don't treat typing as notes while you're typing a value into a slider
    // (Ctrl+click on a slider lets you type a number).
    if (ImGui::GetIO().WantTextInput) return;

    if (ImGui::IsKeyPressed(ImGuiKey_Space, false)) togglePlaying();
    if (ImGui::IsKeyPressed(ImGuiKey_Z, false)) mOctave = std::max(mOctave - 1, 1);
    if (ImGui::IsKeyPressed(ImGuiKey_X, false)) mOctave = std::min(mOctave + 1, 6);

    const ImGuiKey drumKeys[] = {ImGuiKey_1, ImGuiKey_2, ImGuiKey_3, ImGuiKey_4};
    for (int track = 0; track < kDrumTracks; ++track) {
        if (ImGui::IsKeyPressed(drumKeys[track], false)) mEngine.triggerDrum(track);
    }

    for (int i = 0; i < kPianoKeys; ++i) {
        // "false" ignores the automatic key-repeat you get when holding a key down.
        if (ImGui::IsKeyPressed(kPianoComputerKeys[i], false)) {
            mKeyboardHeld[i] = lowestKey() + i;
            noteOn(mKeyboardHeld[i]);
        }
        if (ImGui::IsKeyReleased(kPianoComputerKeys[i]) && mKeyboardHeld[i] != kNoNote) {
            noteOff(mKeyboardHeld[i]);
            mKeyboardHeld[i] = kNoNote;
        }
    }
}

void StepSynthUi::togglePlaying() {
    mPlaying = !mPlaying;
    mEngine.setPlaying(mPlaying);
}

void StepSynthUi::setDrumStep(int track, int step, bool on) {
    mDrumSteps[track][step] = on;
    mEngine.setDrumStep(track, step, on);
}

void StepSynthUi::setSynthStep(int step, int note) {
    mSynthSteps[step] = note;
    mEngine.setSynthStep(step, note);
}

void StepSynthUi::setSynthParam(int param, float value) {
    mSynthParams[param] = value;
    mEngine.setSynthParam(param, value);
}

void StepSynthUi::noteOn(int note) {
    mEngine.synthNoteOn(note);
    mLastNote = note;
}

void StepSynthUi::noteOff(int note) {
    mEngine.synthNoteOff(note);
}

void StepSynthUi::loadDemoPattern() {
    for (int step = 0; step < kSteps; step += 4) mDrumSteps[0][step] = true;  // kick on every beat
    mDrumSteps[1][4] = mDrumSteps[1][12] = true;                               // snare on 2 and 4
    for (int step = 2; step < kSteps; step += 4) mDrumSteps[2][step] = true;  // off-beat hats
    mDrumSteps[3][14] = true;                                                  // one clap

    const int bassline[kSteps] = {36, kNoNote, 36, 48, kNoNote, 36, kNoNote, 43,
                                  36, kNoNote, 39, kNoNote, 36, 48, kNoNote, 46};
    std::copy(std::begin(bassline), std::end(bassline), mSynthSteps.begin());
}

void StepSynthUi::sendEverythingToEngine() {
    mEngine.setPlaying(mPlaying);
    mEngine.setTempo(mTempo);
    mEngine.setSwing((mSwingPercent - 50) / 50.0f);
    for (int track = 0; track < kDrumTracks; ++track) {
        for (int step = 0; step < kSteps; ++step) mEngine.setDrumStep(track, step, mDrumSteps[track][step]);
    }
    for (int step = 0; step < kSteps; ++step) mEngine.setSynthStep(step, mSynthSteps[step]);
    for (int param = 0; param < kNumSynthParams; ++param) mEngine.setSynthParam(param, mSynthParams[param]);
}
