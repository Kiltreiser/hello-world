#include "AudioOutput.h"

#include <cstdio>
#include <cstdlib>

AudioOutput::~AudioOutput() {
    if (mStarted) ma_device_uninit(&mDevice);
}

bool AudioOutput::start() {
    ma_device_config config = ma_device_config_init(ma_device_type_playback);
    config.playback.format = ma_format_f32;
    config.playback.channels = 2;
    config.sampleRate = 0;  // 0 = use the device's own rate, usually 48000 Hz
    config.performanceProfile = ma_performance_profile_low_latency;
    // Small buffers make keys and pads respond quickly, but if they're too small
    // the computer can't keep up and you hear crackles. The default is 3 x 10 ms.
    // To change it, start the app like this:  STEPSYNTH_BUFFER_MS=20 ./stepsynth
    config.periodSizeInMilliseconds = 10;
    if (const char* setting = std::getenv("STEPSYNTH_BUFFER_MS")) {
        int ms = std::atoi(setting);
        if (ms > 0) config.periodSizeInMilliseconds = static_cast<ma_uint32>(ms);
    }
    config.periods = 3;
    config.dataCallback = dataCallback;
    config.pUserData = &mEngine;

    ma_result result = ma_device_init(nullptr, &config, &mDevice);
    if (result != MA_SUCCESS) {
        mError = ma_result_description(result);
        std::fprintf(stderr, "Could not open audio device: %s\n", mError.c_str());
        return false;
    }

    // The engine must know the real sample rate before any audio is made.
    mEngine.setSampleRate(static_cast<float>(mDevice.sampleRate));

    result = ma_device_start(&mDevice);
    if (result != MA_SUCCESS) {
        mError = ma_result_description(result);
        std::fprintf(stderr, "Could not start audio device: %s\n", mError.c_str());
        ma_device_uninit(&mDevice);
        return false;
    }

    mStarted = true;
    std::printf("Audio started: %s\n", description().c_str());
    return true;
}

std::string AudioOutput::description() const {
    if (!mStarted) return "could not open a sound device (" + mError + ")";
    if (mDevice.pContext->backend == ma_backend_null) {
        return "no sound device found, running silently. Check your sound settings, then restart the app.";
    }
    char text[128];
    std::snprintf(text, sizeof(text), "%s, %u Hz, ~%u ms buffer",
                  ma_get_backend_name(mDevice.pContext->backend), mDevice.sampleRate,
                  mDevice.playback.internalPeriodSizeInFrames * mDevice.playback.internalPeriods * 1000 /
                      mDevice.sampleRate);
    return text;
}

bool AudioOutput::isAudible() const {
    return mStarted && mDevice.pContext->backend != ma_backend_null;
}

// Called by miniaudio on its own high-priority audio thread.
void AudioOutput::dataCallback(ma_device* device, void* output, const void* /*input*/, ma_uint32 frameCount) {
    auto* engine = static_cast<AudioEngine*>(device->pUserData);
    engine->render(static_cast<float*>(output), static_cast<int32_t>(frameCount),
                   static_cast<int32_t>(device->playback.channels));
}
