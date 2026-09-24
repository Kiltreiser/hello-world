// Desktop test for the audio engine. No phone or Android SDK needed.
//
// It checks that sequencer steps land at the exact right sample, that the
// output never contains invalid or clipping values, and writes demo.wav so you
// can listen to the result.
//
// Build and run from the StepSynth folder (needs a C++17 compiler):
//   g++ -std=c++17 -O2 -I app/src/main/cpp/engine engine-tests/render_test.cpp
//       app/src/main/cpp/engine/AudioEngine.cpp -o render_test
//   ./render_test

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <vector>

#include "AudioEngine.h"

static int gFailures = 0;

static void check(bool ok, const char* what) {
    std::printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) gFailures++;
}

static void writeWav(const char* path, const std::vector<float>& samples, int sampleRate, int channels) {
    std::ofstream f(path, std::ios::binary);
    auto u32 = [&](uint32_t v) { f.write(reinterpret_cast<const char*>(&v), 4); };
    auto u16 = [&](uint16_t v) { f.write(reinterpret_cast<const char*>(&v), 2); };
    uint32_t dataBytes = static_cast<uint32_t>(samples.size() * 2);
    f.write("RIFF", 4); u32(36 + dataBytes); f.write("WAVE", 4);
    f.write("fmt ", 4); u32(16); u16(1); u16(channels); u32(sampleRate);
    u32(sampleRate * channels * 2); u16(channels * 2); u16(16);
    f.write("data", 4); u32(dataBytes);
    for (float s : samples) u16(static_cast<uint16_t>(static_cast<int16_t>(s * 32767.0f)));
}

// Renders one frame at a time and records the sample index where each step starts.
static std::vector<long> measureStepStarts(float tempo, float swing, int sampleRate, int steps) {
    AudioEngine engine;
    engine.setSampleRate(static_cast<float>(sampleRate));
    engine.setTempo(tempo);
    engine.setSwing(swing);
    engine.setPlaying(true);
    std::vector<long> starts;
    float frame[2];
    int last = -1;
    for (long i = 0; static_cast<int>(starts.size()) < steps; ++i) {
        engine.render(frame, 1, 2);
        int now = engine.currentStep();
        if (now != last) {
            starts.push_back(i);
            last = now;
        }
    }
    return starts;
}

int main() {
    const int sr = 48000;

    // 1. Timing: at 120 BPM a 16th note is 0.125 s = 6000 samples.
    {
        auto starts = measureStepStarts(120.0f, 0.0f, sr, 33);
        bool exact = true;
        for (size_t i = 0; i < starts.size(); ++i) {
            if (starts[i] != static_cast<long>(i) * 6000) exact = false;
        }
        check(exact, "straight timing: every step starts exactly 6000 samples apart (2 bars)");
    }

    // 2. Swing: 0.25 swing makes steps alternate 7500 / 4500 samples.
    {
        auto starts = measureStepStarts(120.0f, 0.25f, sr, 17);
        bool ok = true;
        for (size_t i = 1; i < starts.size(); ++i) {
            long len = starts[i] - starts[i - 1];
            long expected = ((i - 1) % 2 == 0) ? 7500 : 4500;
            if (len != expected) ok = false;
        }
        check(ok, "swing timing: steps alternate long/short and pairs stay in time");
    }

    // 3. No drift at a tempo where the step length isn't a whole number of samples.
    {
        // 133 BPM at 44.1 kHz: 4973.68... samples per step.
        auto starts = measureStepStarts(133.0f, 0.0f, 44100, 16 * 8 + 1);
        double expected = 128 * 44100.0 * 60.0 / (133.0 * 4.0);
        check(std::fabs(starts.back() - expected) <= 1.0, "no drift after 8 bars at an uneven tempo");
    }

    // 4. Render a demo pattern in phone-sized blocks and check the audio itself.
    AudioEngine engine;
    engine.setSampleRate(static_cast<float>(sr));
    engine.setTempo(120.0f);
    for (int s = 0; s < 16; s += 4) engine.setDrumStep(0, s, true);    // kick
    engine.setDrumStep(1, 4, true);                                    // snare
    engine.setDrumStep(1, 12, true);
    for (int s = 2; s < 16; s += 4) engine.setDrumStep(2, s, true);    // hat
    engine.setDrumStep(3, 14, true);                                   // clap
    const int bass[16] = {36, -1, 36, 48, -1, 36, -1, 43, 36, -1, 39, -1, 36, 48, -1, 46};
    for (int s = 0; s < 16; ++s) engine.setSynthStep(s, bass[s]);
    engine.setSynthParam(kParamResonance, 0.6f);
    engine.setPlaying(true);

    const int channels = 2, block = 192;
    const int totalFrames = sr * 8;  // 4 bars at 120 BPM
    std::vector<float> audio(static_cast<size_t>(totalFrames) * channels);
    for (int pos = 0; pos < totalFrames; pos += block) {
        if (pos == sr * 4) {
            // Halfway through, play a live note and a live drum hit as if tapped on screen.
            engine.synthNoteOn(60);
            engine.triggerDrum(3);
        }
        if (pos == sr * 4 + sr / 4) engine.synthNoteOff(60);
        if (pos == sr * 6) engine.setSynthParam(kParamWaveform, 1.0f);  // switch to square
        engine.render(&audio[static_cast<size_t>(pos) * channels], block, channels);
    }

    bool finite = true;
    float peak = 0.0f;
    double sumSquares = 0.0;
    for (float s : audio) {
        if (!std::isfinite(s)) finite = false;
        peak = std::max(peak, std::fabs(s));
        sumSquares += s * s;
    }
    double rms = std::sqrt(sumSquares / audio.size());
    std::printf("      peak %.3f, rms %.3f\n", peak, rms);
    check(finite, "no NaN or infinite samples");
    check(peak <= 1.0f, "never exceeds full scale");
    check(rms > 0.05, "pattern is actually audible");

    // 5. Stopping silences the synth and resets the playhead.
    engine.setPlaying(false);
    std::vector<float> tail(static_cast<size_t>(sr) * 2 * channels);
    engine.render(tail.data(), sr * 2, channels);
    float tailPeak = 0.0f;
    for (size_t i = tail.size() - 2000; i < tail.size(); ++i) tailPeak = std::max(tailPeak, std::fabs(tail[i]));
    check(engine.currentStep() == -1, "playhead resets to -1 when stopped");
    check(tailPeak < 0.001f, "silent two seconds after stopping");

    writeWav("demo.wav", audio, sr, channels);
    std::printf("\nWrote demo.wav (4 bars). %s\n", gFailures == 0 ? "All checks passed." : "Some checks FAILED.");
    return gFailures == 0 ? 0 : 1;
}
