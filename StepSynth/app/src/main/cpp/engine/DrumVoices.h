// Synthesized drum sounds. They are generated from oscillators and noise, so
// the app doesn't need any sample files yet.
#pragma once

#include "Dsp.h"

// Sine wave with a fast downward pitch sweep.
class Kick {
public:
    void setSampleRate(float sr) {
        mSampleRate = sr;
        mAmpCoef = dsp::decayCoef(0.2f, sr);
        mPitchCoef = dsp::decayCoef(0.04f, sr);
    }
    void trigger() {
        mPhase = 0.0f;
        mAmp = 1.0f;
        mPitchEnv = 1.0f;
    }
    float process() {
        if (mAmp < 0.0001f) return 0.0f;
        float freq = 45.0f + 110.0f * mPitchEnv;
        mPhase += freq / mSampleRate;
        if (mPhase >= 1.0f) mPhase -= 1.0f;
        float out = std::tanh(1.5f * std::sin(dsp::kTwoPi * mPhase)) * mAmp;
        mAmp *= mAmpCoef;
        mPitchEnv *= mPitchCoef;
        return out;
    }

private:
    float mSampleRate = 48000.0f;
    float mPhase = 0.0f, mAmp = 0.0f, mPitchEnv = 0.0f;
    float mAmpCoef = 0.0f, mPitchCoef = 0.0f;
};

// Short tone for the "body" plus highpassed noise for the "snares".
class Snare {
public:
    void setSampleRate(float sr) {
        mSampleRate = sr;
        mToneCoef = dsp::decayCoef(0.08f, sr);
        mNoiseCoef = dsp::decayCoef(0.16f, sr);
        mFilter.set(1500.0f, 0.7f, sr);
    }
    void trigger() {
        mPhase = 0.0f;
        mToneAmp = 1.0f;
        mNoiseAmp = 1.0f;
    }
    float process() {
        if (mNoiseAmp < 0.0001f) return 0.0f;
        mPhase += 185.0f / mSampleRate;
        if (mPhase >= 1.0f) mPhase -= 1.0f;
        float tone = std::sin(dsp::kTwoPi * mPhase) * mToneAmp;
        mFilter.process(mNoise.next());
        float noise = mFilter.highpass * mNoiseAmp;
        mToneAmp *= mToneCoef;
        mNoiseAmp *= mNoiseCoef;
        return 0.5f * tone + 0.6f * noise;
    }

private:
    float mSampleRate = 48000.0f;
    float mPhase = 0.0f, mToneAmp = 0.0f, mNoiseAmp = 0.0f;
    float mToneCoef = 0.0f, mNoiseCoef = 0.0f;
    dsp::Noise mNoise;
    dsp::Svf mFilter;
};

// Very short burst of high-frequency noise.
class HiHat {
public:
    void setSampleRate(float sr) {
        mAmpCoef = dsp::decayCoef(0.045f, sr);
        mFilter.set(8000.0f, 0.7f, sr);
    }
    void trigger() { mAmp = 1.0f; }
    float process() {
        if (mAmp < 0.0001f) return 0.0f;
        mFilter.process(mNoise.next());
        float out = mFilter.highpass * mAmp;
        mAmp *= mAmpCoef;
        return out;
    }

private:
    float mAmp = 0.0f, mAmpCoef = 0.0f;
    dsp::Noise mNoise;
    dsp::Svf mFilter;
};

// Bandpassed noise with three quick bursts (like several hands) and then a tail.
class Clap {
public:
    void setSampleRate(float sr) {
        mBurstLength = static_cast<int>(0.009f * sr);
        mBurstCoef = dsp::decayCoef(0.004f, sr);
        mTailCoef = dsp::decayCoef(0.14f, sr);
        mFilter.set(1200.0f, 1.5f, sr);
    }
    void trigger() {
        mCounter = 0;
        mAmp = 1.0f;
        mActive = true;
    }
    float process() {
        if (!mActive) return 0.0f;
        constexpr int kBursts = 3;
        if (mCounter < kBursts * mBurstLength) {
            if (mCounter % mBurstLength == 0) mAmp = 1.0f;
            mAmp *= mBurstCoef;
        } else {
            if (mCounter == kBursts * mBurstLength) mAmp = 0.8f;
            mAmp *= mTailCoef;
            if (mAmp < 0.0001f) mActive = false;
        }
        mCounter++;
        mFilter.process(mNoise.next());
        return 2.0f * mFilter.bandpass * mAmp;
    }

private:
    bool mActive = false;
    int mCounter = 0, mBurstLength = 1;
    float mAmp = 0.0f, mBurstCoef = 0.0f, mTailCoef = 0.0f;
    dsp::Noise mNoise;
    dsp::Svf mFilter;
};
