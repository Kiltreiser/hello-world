// Connects the AudioEngine to the phone's audio output using Google's Oboe
// library. Oboe picks the fastest audio path the phone supports (AAudio on
// Android 8.1+, OpenSL ES on older phones).
#pragma once

#include <memory>
#include <mutex>

#include <oboe/Oboe.h>

#include "engine/AudioEngine.h"

class OboePlayer : public oboe::AudioStreamDataCallback, public oboe::AudioStreamErrorCallback {
public:
    explicit OboePlayer(AudioEngine& engine) : mEngine(engine) {}

    bool start();
    void stop();

    // Called by Oboe on its high-priority audio thread.
    oboe::DataCallbackResult onAudioReady(oboe::AudioStream* stream, void* audioData,
                                          int32_t numFrames) override;

    // Called when the stream dies, e.g. when headphones are plugged in or removed.
    void onErrorAfterClose(oboe::AudioStream* stream, oboe::Result error) override;

private:
    bool openAndStart();

    AudioEngine& mEngine;
    std::shared_ptr<oboe::AudioStream> mStream;
    std::mutex mLock;
    bool mWanted = false;  // true between start() and stop()
};
