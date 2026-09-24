// The heart of the app: owns the sequencer, the synth and the drums, and mixes
// them into audio.
//
// Two threads use this class:
//  - The UI thread calls the "control" methods (setTempo, setDrumStep, ...).
//    These only write to atomics or push to a lock-free queue, so they're safe
//    to call at any time.
//  - The audio thread calls render() whenever the phone needs more audio.
//
// This file has no Android dependencies, so the engine can also be compiled and
// tested on a desktop computer (see engine-tests/).
#pragma once

#include <array>
#include <atomic>
#include <cstdint>

#include "DrumVoices.h"
#include "SpscQueue.h"
#include "SynthVoice.h"

class AudioEngine {
public:
    static constexpr int kNumSteps = 16;
    static constexpr int kNumDrumTracks = 4;  // 0 kick, 1 snare, 2 hat, 3 clap
    static constexpr int kNoNote = -1;

    AudioEngine();

    // Call before audio starts (not while render() may be running).
    void setSampleRate(float sampleRate);

    // Audio thread: fills `out` with interleaved samples (L R L R ... for stereo).
    void render(float* out, int32_t numFrames, int32_t numChannels);

    // ---- Control methods, called from the UI thread ----
    void setPlaying(bool playing) { mPlaying.store(playing); }
    void setTempo(float bpm);
    void setSwing(float amount);  // 0 = straight, 0.5 = maximum swing
    void setDrumStep(int track, int step, bool on);
    void setSynthStep(int step, int note);  // note = kNoNote to clear the step
    void setSynthParam(int param, float value);
    void triggerDrum(int track);
    void synthNoteOn(int note);
    void synthNoteOff(int note);

    // The step that is playing now, or -1 when stopped. Used to draw the playhead.
    int currentStep() const { return mPlayhead.load(); }

private:
    struct Event {
        enum Type { DrumHit, NoteOn, NoteOff } type;
        int value;
    };

    void handleEvents();
    void fireStep(int step);
    double stepLengthInSamples(int step) const;
    void playDrum(int track);

    // Shared between threads (atomics)
    std::atomic<bool> mPlaying{false};
    std::atomic<float> mTempo{120.0f};
    std::atomic<float> mSwing{0.0f};
    std::array<std::atomic<bool>, kNumDrumTracks * kNumSteps> mDrumSteps;
    std::array<std::atomic<int>, kNumSteps> mSynthSteps;
    std::array<std::atomic<float>, kNumSynthParams> mSynthParams;
    std::atomic<int> mPlayhead{-1};
    SpscQueue<Event, 256> mEvents;

    // Only touched by the audio thread
    float mSampleRate = 48000.0f;
    bool mWasPlaying = false;
    int mNextStep = 0;
    double mSamplesUntilNextStep = 0.0;
    int mSequencedNote = kNoNote;
    int mGateSamplesLeft = 0;

    SynthVoice mSynth;
    Kick mKick;
    Snare mSnare;
    HiHat mHat;
    Clap mClap;
};
