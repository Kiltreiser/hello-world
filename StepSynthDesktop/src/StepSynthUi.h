// The window's contents: the pattern grid, pads, keyboard and synth controls.
//
// Like StepSynthViewModel in the Android app, this keeps its own copy of the
// pattern for drawing, and sends every change on to the AudioEngine.
#pragma once

#include <array>
#include <string>

#include "AudioEngine.h"

class StepSynthUi {
public:
    explicit StepSynthUi(AudioEngine& engine);

    // Draws one frame. Call between ImGui::NewFrame() and ImGui::Render().
    void draw(const std::string& audioStatus, bool audioOk);

private:
    static constexpr int kSteps = AudioEngine::kNumSteps;
    static constexpr int kDrumTracks = AudioEngine::kNumDrumTracks;
    static constexpr int kNoNote = AudioEngine::kNoNote;
    static constexpr int kPianoKeys = 13;  // one octave plus the top C

    void drawTransport();
    void drawPatternGrid();
    void drawDrumPads();
    void drawKeyboard();
    void drawSynthControls();
    void drawStatusBar(const std::string& audioStatus, bool audioOk);
    void handleComputerKeyboard();

    void togglePlaying();
    void setDrumStep(int track, int step, bool on);
    void setSynthStep(int step, int note);
    void setSynthParam(int param, float value);
    void noteOn(int note);
    void noteOff(int note);
    int lowestKey() const { return (mOctave + 1) * 12; }

    void loadDemoPattern();
    void sendEverythingToEngine();

    AudioEngine& mEngine;

    bool mDrumSteps[kDrumTracks][kSteps] = {};
    std::array<int, kSteps> mSynthSteps{};
    std::array<float, kNumSynthParams> mSynthParams{0.0f, 0.4f, 0.6f, 0.5f, 0.3f};
    bool mPlaying = false;
    float mTempo = 120.0f;
    int mSwingPercent = 50;  // 50% = straight, 75% = maximum swing
    int mOctave = 3;         // lowest key is C3 (MIDI note 48)
    int mLastNote = 48;      // clicking an empty synth step puts this note there

    // Which note each piano key is holding (kNoNote if none), so releasing a key
    // stops the right note even if the octave changed while it was held.
    std::array<int, kPianoKeys> mMouseHeld{};
    std::array<int, kPianoKeys> mKeyboardHeld{};
};
