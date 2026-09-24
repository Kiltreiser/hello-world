package com.kiltreiser.stepsynth.audio

/**
 * Kotlin's doorway into the C++ audio engine.
 *
 * Each `external fun` is implemented in app/src/main/cpp/jni_bridge.cpp. The
 * sound itself is generated in C++ because it has to run without pauses, and
 * Kotlin's garbage collector can pause at any moment.
 */
object NativeEngine {
    init {
        System.loadLibrary("stepsynth")
    }

    const val STEPS = 16
    const val DRUM_TRACKS = 4
    const val NO_NOTE = -1

    // Must match the SynthParam enum in engine/SynthVoice.h
    const val PARAM_WAVEFORM = 0
    const val PARAM_CUTOFF = 1
    const val PARAM_RESONANCE = 2
    const val PARAM_ENV_AMOUNT = 3
    const val PARAM_DECAY = 4

    /** Opens the audio output. Returns false if the phone refused. */
    external fun start(): Boolean
    external fun stop()

    external fun setPlaying(playing: Boolean)
    external fun setTempo(bpm: Float)
    /** 0 = straight, 0.5 = maximum swing. */
    external fun setSwing(amount: Float)

    external fun setDrumStep(track: Int, step: Int, on: Boolean)
    /** note is a MIDI note number (60 = middle C), or NO_NOTE to clear the step. */
    external fun setSynthStep(step: Int, note: Int)
    /** value is 0..1 */
    external fun setSynthParam(param: Int, value: Float)

    external fun triggerDrum(track: Int)
    external fun synthNoteOn(note: Int)
    external fun synthNoteOff(note: Int)

    /** The step playing right now (0..15), or -1 when stopped. */
    external fun getCurrentStep(): Int
}
