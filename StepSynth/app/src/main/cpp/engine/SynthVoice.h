// A monophonic (one note at a time) subtractive synth voice:
// oscillator -> resonant lowpass filter -> amplifier, with envelopes
// controlling the filter and the volume.
#pragma once

#include "Dsp.h"

enum SynthParam {
    kParamWaveform = 0,   // 0 = saw, 1 = square
    kParamCutoff = 1,     // 0..1, filter brightness
    kParamResonance = 2,  // 0..1, filter "squelch"
    kParamEnvAmount = 3,  // 0..1, how much the envelope opens the filter
    kParamDecay = 4,      // 0..1, note length / pluckiness
    kNumSynthParams = 5,
};

class SynthVoice {
public:
    void setSampleRate(float sampleRate) {
        mSampleRate = sampleRate;
        updateEnvelopes();
    }

    void setParams(float waveform, float cutoff, float resonance, float envAmount, float decay) {
        mSquare = waveform >= 0.5f;
        mCutoff = cutoff;
        mResonance = resonance;
        mEnvAmount = envAmount;
        if (decay != mDecay) {
            mDecay = decay;
            updateEnvelopes();
        }
    }

    void noteOn(int note) {
        mNote = note;
        mFreq = dsp::midiToHz(static_cast<float>(note));
        mAmpEnv.gateOn();
        mFilterEnv.gateOn();
    }

    // Only release if this is the note that is currently sounding, so letting
    // go of an old key doesn't cut off a newer one.
    void noteOff(int note) {
        if (note != mNote) return;
        mAmpEnv.gateOff();
        mFilterEnv.gateOff();
    }

    float process() {
        if (!mAmpEnv.isActive()) return 0.0f;

        // Oscillator
        float dt = mFreq / mSampleRate;
        float osc;
        if (mSquare) {
            osc = (mPhase < 0.5f ? 1.0f : -1.0f);
            osc += dsp::polyBlep(mPhase, dt);
            osc -= dsp::polyBlep(std::fmod(mPhase + 0.5f, 1.0f), dt);
        } else {
            osc = 2.0f * mPhase - 1.0f - dsp::polyBlep(mPhase, dt);
        }
        mPhase += dt;
        if (mPhase >= 1.0f) mPhase -= 1.0f;

        // Filter: base cutoff spans 40 Hz..20 kHz, the envelope adds up to 5 octaves.
        float filterEnv = mFilterEnv.next();
        float cutoffHz = 40.0f * std::pow(2.0f, mCutoff * 9.0f + mEnvAmount * 5.0f * filterEnv);
        mFilter.set(cutoffHz, 0.6f + mResonance * 11.0f, mSampleRate);
        mFilter.process(osc);

        return mFilter.lowpass * mAmpEnv.next();
    }

private:
    void updateEnvelopes() {
        float decaySeconds = 0.03f + mDecay * mDecay * 1.5f;
        mAmpEnv.set(0.002f, decaySeconds, 0.35f, 0.06f, mSampleRate);
        mFilterEnv.set(0.001f, decaySeconds * 0.7f, 0.0f, 0.06f, mSampleRate);
    }

    float mSampleRate = 48000.0f;
    int mNote = -1;
    float mFreq = 440.0f;
    float mPhase = 0.0f;

    bool mSquare = false;
    float mCutoff = 0.4f, mResonance = 0.3f, mEnvAmount = 0.5f, mDecay = 0.3f;

    dsp::Svf mFilter;
    dsp::Adsr mAmpEnv;
    dsp::Adsr mFilterEnv;
};
