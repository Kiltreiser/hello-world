#include "AudioEngine.h"

#include <algorithm>
#include <cmath>

AudioEngine::AudioEngine() {
    // std::atomic doesn't zero itself inside arrays in C++17, so set every value.
    for (auto& step : mDrumSteps) step.store(false);
    for (auto& step : mSynthSteps) step.store(kNoNote);
    mSynthParams[kParamWaveform].store(0.0f);
    mSynthParams[kParamCutoff].store(0.4f);
    mSynthParams[kParamResonance].store(0.3f);
    mSynthParams[kParamEnvAmount].store(0.5f);
    mSynthParams[kParamDecay].store(0.3f);
    setSampleRate(48000.0f);
}

void AudioEngine::setSampleRate(float sampleRate) {
    mSampleRate = sampleRate;
    mSynth.setSampleRate(sampleRate);
    mKick.setSampleRate(sampleRate);
    mSnare.setSampleRate(sampleRate);
    mHat.setSampleRate(sampleRate);
    mClap.setSampleRate(sampleRate);
}

// ---- Control methods (UI thread) ----

void AudioEngine::setTempo(float bpm) {
    mTempo.store(std::clamp(bpm, 30.0f, 300.0f));
}

void AudioEngine::setSwing(float amount) {
    mSwing.store(std::clamp(amount, 0.0f, 0.5f));
}

void AudioEngine::setDrumStep(int track, int step, bool on) {
    if (track < 0 || track >= kNumDrumTracks || step < 0 || step >= kNumSteps) return;
    mDrumSteps[track * kNumSteps + step].store(on);
}

void AudioEngine::setSynthStep(int step, int note) {
    if (step < 0 || step >= kNumSteps) return;
    mSynthSteps[step].store(note);
}

void AudioEngine::setSynthParam(int param, float value) {
    if (param < 0 || param >= kNumSynthParams) return;
    mSynthParams[param].store(std::clamp(value, 0.0f, 1.0f));
}

void AudioEngine::triggerDrum(int track) {
    mEvents.push({Event::DrumHit, track});
}

void AudioEngine::synthNoteOn(int note) {
    mEvents.push({Event::NoteOn, note});
}

void AudioEngine::synthNoteOff(int note) {
    mEvents.push({Event::NoteOff, note});
}

// ---- Audio thread ----

void AudioEngine::render(float* out, int32_t numFrames, int32_t numChannels) {
    handleEvents();
    mSynth.setParams(mSynthParams[kParamWaveform].load(), mSynthParams[kParamCutoff].load(),
                     mSynthParams[kParamResonance].load(), mSynthParams[kParamEnvAmount].load(),
                     mSynthParams[kParamDecay].load());

    bool playing = mPlaying.load();
    if (playing && !mWasPlaying) {
        // Just pressed play: start from step 1 immediately.
        mNextStep = 0;
        mSamplesUntilNextStep = 0.0;
    } else if (!playing && mWasPlaying) {
        // Just pressed stop: silence any sequenced synth note.
        if (mSequencedNote != kNoNote) mSynth.noteOff(mSequencedNote);
        mSequencedNote = kNoNote;
        mGateSamplesLeft = 0;
        mPlayhead.store(-1);
    }
    mWasPlaying = playing;

    for (int32_t frame = 0; frame < numFrames; ++frame) {
        // The sequencer clock counts individual samples, so steps land at exactly
        // the right moment no matter how the audio is split into blocks.
        if (playing) {
            if (mSamplesUntilNextStep <= 0.0) {
                fireStep(mNextStep);
                mSamplesUntilNextStep += stepLengthInSamples(mNextStep);
                mNextStep = (mNextStep + 1) % kNumSteps;
            }
            mSamplesUntilNextStep -= 1.0;

            if (mGateSamplesLeft > 0 && --mGateSamplesLeft == 0) {
                mSynth.noteOff(mSequencedNote);
                mSequencedNote = kNoNote;
            }
        }

        float mix = 0.35f * mSynth.process()
                  + 0.9f * mKick.process()
                  + 0.6f * mSnare.process()
                  + 0.35f * mHat.process()
                  + 0.5f * mClap.process();

        // Soft clipping: keeps loud moments from distorting harshly.
        float sample = std::tanh(mix);

        for (int32_t ch = 0; ch < numChannels; ++ch) {
            out[frame * numChannels + ch] = sample;
        }
    }
}

void AudioEngine::handleEvents() {
    Event event{};
    while (mEvents.pop(event)) {
        switch (event.type) {
            case Event::DrumHit:
                playDrum(event.value);
                break;
            case Event::NoteOn:
                mSynth.noteOn(event.value);
                break;
            case Event::NoteOff:
                mSynth.noteOff(event.value);
                break;
        }
    }
}

void AudioEngine::fireStep(int step) {
    mPlayhead.store(step);

    for (int track = 0; track < kNumDrumTracks; ++track) {
        if (mDrumSteps[track * kNumSteps + step].load()) playDrum(track);
    }

    int note = mSynthSteps[step].load();
    if (note != kNoNote) {
        mSynth.noteOn(note);
        mSequencedNote = note;
        // Hold the note for half a step, then release it.
        mGateSamplesLeft = std::max(1, static_cast<int>(stepLengthInSamples(step) * 0.5));
    }
}

double AudioEngine::stepLengthInSamples(int step) const {
    // A 16-step pattern is one bar of 16th notes: 4 steps per beat.
    double base = mSampleRate * 60.0 / (mTempo.load() * 4.0);
    // Swing makes each even step longer and the following odd step shorter by
    // the same amount, so pairs of steps still add up to the same length.
    double swing = mSwing.load();
    return (step % 2 == 0) ? base * (1.0 + swing) : base * (1.0 - swing);
}

void AudioEngine::playDrum(int track) {
    switch (track) {
        case 0: mKick.trigger(); break;
        case 1: mSnare.trigger(); break;
        case 2: mHat.trigger(); break;
        case 3: mClap.trigger(); break;
        default: break;
    }
}
