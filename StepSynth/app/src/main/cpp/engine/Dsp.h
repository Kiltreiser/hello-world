// Small DSP building blocks shared by the synth and drum voices.
//
// Everything here runs on the audio thread, so none of it allocates memory,
// takes locks, or does anything that could block.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace dsp {

constexpr float kPi = 3.14159265358979f;
constexpr float kTwoPi = 2.0f * kPi;

// MIDI note number to frequency in Hz. Note 69 is A4 = 440 Hz, 60 is middle C.
inline float midiToHz(float note) {
    return 440.0f * std::pow(2.0f, (note - 69.0f) / 12.0f);
}

// Per-sample multiplier that makes a value decay to about 37% (1/e) of its
// starting level after `seconds`. Multiply by it once per sample.
inline float decayCoef(float seconds, float sampleRate) {
    return std::exp(-1.0f / (std::max(seconds, 0.0001f) * sampleRate));
}

// Fast white noise in the range -1..1 (xorshift random number generator).
class Noise {
public:
    float next() {
        mState ^= mState << 13;
        mState ^= mState >> 17;
        mState ^= mState << 5;
        return static_cast<float>(mState) * (2.0f / 4294967296.0f) - 1.0f;
    }

private:
    uint32_t mState = 22222;
};

// PolyBLEP smooths the sharp jumps in saw and square waves. Without it,
// high notes produce harsh, out-of-tune "aliasing" tones.
// t is the oscillator phase (0..1), dt is the phase increment per sample.
inline float polyBlep(float t, float dt) {
    if (t < dt) {
        t /= dt;
        return t + t - t * t - 1.0f;
    }
    if (t > 1.0f - dt) {
        t = (t - 1.0f) / dt;
        return t * t + t + t + 1.0f;
    }
    return 0.0f;
}

// State-variable filter (Andrew Simper's "Cytomic" design). One call to
// process() gives lowpass, bandpass and highpass outputs at the same time.
class Svf {
public:
    // q around 0.7 is smooth; higher values give a resonant peak.
    void set(float cutoffHz, float q, float sampleRate) {
        cutoffHz = std::clamp(cutoffHz, 20.0f, sampleRate * 0.45f);
        float g = std::tan(kPi * cutoffHz / sampleRate);
        mK = 1.0f / q;
        mA1 = 1.0f / (1.0f + g * (g + mK));
        mA2 = g * mA1;
        mA3 = g * mA2;
    }

    void process(float in) {
        float v3 = in - mIc2;
        float v1 = mA1 * mIc1 + mA2 * v3;
        float v2 = mIc2 + mA2 * mIc1 + mA3 * v3;
        mIc1 = 2.0f * v1 - mIc1;
        mIc2 = 2.0f * v2 - mIc2;
        lowpass = v2;
        bandpass = v1;
        highpass = in - mK * v1 - v2;
    }

    void reset() { mIc1 = mIc2 = 0.0f; }

    float lowpass = 0.0f;
    float bandpass = 0.0f;
    float highpass = 0.0f;

private:
    float mK = 1.0f, mA1 = 0.0f, mA2 = 0.0f, mA3 = 0.0f;
    float mIc1 = 0.0f, mIc2 = 0.0f;
};

// Attack / Decay / Sustain / Release envelope, output 0..1.
class Adsr {
public:
    void set(float attackS, float decayS, float sustain, float releaseS, float sampleRate) {
        mAttackInc = 1.0f / (std::max(attackS, 0.0001f) * sampleRate);
        mDecayCoef = decayCoef(decayS, sampleRate);
        mSustain = sustain;
        mReleaseCoef = decayCoef(releaseS, sampleRate);
    }

    // Retriggering keeps the current level instead of jumping to 0, which avoids clicks.
    void gateOn() { mStage = Stage::Attack; }
    void gateOff() {
        if (mStage != Stage::Idle) mStage = Stage::Release;
    }
    bool isActive() const { return mStage != Stage::Idle; }

    float next() {
        switch (mStage) {
            case Stage::Attack:
                mValue += mAttackInc;
                if (mValue >= 1.0f) {
                    mValue = 1.0f;
                    mStage = Stage::Decay;
                }
                break;
            case Stage::Decay:
                mValue = mSustain + (mValue - mSustain) * mDecayCoef;
                if (mValue - mSustain < 0.0001f) mStage = Stage::Sustain;
                break;
            case Stage::Sustain:
                mValue = mSustain;
                break;
            case Stage::Release:
                mValue *= mReleaseCoef;
                if (mValue < 0.00001f) {
                    mValue = 0.0f;
                    mStage = Stage::Idle;
                }
                break;
            case Stage::Idle:
                break;
        }
        return mValue;
    }

private:
    enum class Stage { Idle, Attack, Decay, Sustain, Release };
    Stage mStage = Stage::Idle;
    float mValue = 0.0f;
    float mAttackInc = 0.0f, mDecayCoef = 0.0f, mSustain = 0.0f, mReleaseCoef = 0.0f;
};

}  // namespace dsp
