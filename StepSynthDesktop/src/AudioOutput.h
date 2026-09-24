// Connects the AudioEngine to the computer's sound output using miniaudio.
// This plays the same role as OboePlayer does in the Android app.
#pragma once

#include <string>

#include <miniaudio.h>

#include "AudioEngine.h"

class AudioOutput {
public:
    explicit AudioOutput(AudioEngine& engine) : mEngine(engine) {}
    ~AudioOutput();

    // Returns false if no sound device could be opened.
    bool start();

    // A short human-readable description, e.g. "PulseAudio, 48000 Hz, ~10 ms".
    std::string description() const;

    // True if sound is really coming out, rather than going to miniaudio's
    // silent "Null" fallback device.
    bool isAudible() const;

private:
    static void dataCallback(ma_device* device, void* output, const void* input, ma_uint32 frameCount);

    AudioEngine& mEngine;
    ma_device mDevice{};
    bool mStarted = false;
    std::string mError;
};
