#include "OboePlayer.h"

#include <android/log.h>

#define LOG_TAG "StepSynth"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

bool OboePlayer::start() {
    std::lock_guard<std::mutex> lock(mLock);
    mWanted = true;
    return openAndStart();
}

void OboePlayer::stop() {
    std::lock_guard<std::mutex> lock(mLock);
    mWanted = false;
    if (mStream) {
        mStream->stop();
        mStream->close();
        mStream.reset();
    }
}

bool OboePlayer::openAndStart() {
    if (mStream) return true;

    oboe::AudioStreamBuilder builder;
    builder.setDirection(oboe::Direction::Output)
        ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
        ->setSharingMode(oboe::SharingMode::Exclusive)
        ->setFormat(oboe::AudioFormat::Float)
        ->setChannelCount(oboe::ChannelCount::Stereo)
        ->setDataCallback(this)
        ->setErrorCallback(this);

    oboe::Result result = builder.openStream(mStream);
    if (result != oboe::Result::OK) {
        LOGE("Failed to open audio stream: %s", oboe::convertToText(result));
        mStream.reset();
        return false;
    }

    // Use the phone's actual sample rate (often 48000 Hz, sometimes 44100 Hz).
    mEngine.setSampleRate(static_cast<float>(mStream->getSampleRate()));

    // A buffer of two "bursts" is a common low-latency setting that still
    // leaves some headroom against glitches.
    mStream->setBufferSizeInFrames(mStream->getFramesPerBurst() * 2);

    result = mStream->requestStart();
    if (result != oboe::Result::OK) {
        LOGE("Failed to start audio stream: %s", oboe::convertToText(result));
        mStream->close();
        mStream.reset();
        return false;
    }

    LOGI("Audio started: %d Hz, burst %d frames, buffer %d frames, %s",
         mStream->getSampleRate(), mStream->getFramesPerBurst(), mStream->getBufferSizeInFrames(),
         mStream->getAudioApi() == oboe::AudioApi::AAudio ? "AAudio" : "OpenSL ES");
    return true;
}

oboe::DataCallbackResult OboePlayer::onAudioReady(oboe::AudioStream* stream, void* audioData,
                                                  int32_t numFrames) {
    mEngine.render(static_cast<float*>(audioData), numFrames, stream->getChannelCount());
    return oboe::DataCallbackResult::Continue;
}

void OboePlayer::onErrorAfterClose(oboe::AudioStream* /*stream*/, oboe::Result error) {
    LOGE("Audio stream closed: %s", oboe::convertToText(error));
    std::lock_guard<std::mutex> lock(mLock);
    mStream.reset();
    // "Disconnected" means the output device changed, so reopen on the new one.
    if (mWanted && error == oboe::Result::ErrorDisconnected) openAndStart();
}
