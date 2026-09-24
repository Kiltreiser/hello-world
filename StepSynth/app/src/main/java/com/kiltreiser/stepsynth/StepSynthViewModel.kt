package com.kiltreiser.stepsynth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.toMutableStateList
import androidx.lifecycle.ViewModel
import com.kiltreiser.stepsynth.audio.NativeEngine
import com.kiltreiser.stepsynth.audio.NativeEngine.DRUM_TRACKS
import com.kiltreiser.stepsynth.audio.NativeEngine.NO_NOTE
import com.kiltreiser.stepsynth.audio.NativeEngine.STEPS

/** Tracks 0-3 are drums, track 4 is the synth. */
const val SYNTH_TRACK = 4
val TRACK_NAMES = listOf("Kick", "Snare", "Hat", "Clap", "Synth")

/**
 * Holds everything the screen shows and sends every change on to the audio
 * engine. A ViewModel survives screen rotation, so the pattern isn't lost.
 *
 * The rule of thumb: the UI reads state from here and calls functions here.
 * It never talks to NativeEngine directly (except to read the playhead).
 */
class StepSynthViewModel : ViewModel() {

    val drumSteps: List<SnapshotStateList<Boolean>> =
        List(DRUM_TRACKS) { MutableList(STEPS) { false }.toMutableStateList() }
    val synthSteps: SnapshotStateList<Int> = MutableList(STEPS) { NO_NOTE }.toMutableStateList()

    // Order matches the PARAM_* constants in NativeEngine.
    val synthParams: SnapshotStateList<Float> = mutableListOf(0f, 0.4f, 0.6f, 0.5f, 0.3f).toMutableStateList()

    var selectedTrack by mutableIntStateOf(0)
        private set
    var isPlaying by mutableStateOf(false)
        private set
    var tempo by mutableFloatStateOf(120f)
        private set
    var swing by mutableFloatStateOf(0f)
        private set

    /** Octave shown on the keyboard. 3 means the lowest key is C3 (MIDI note 48). */
    var octave by mutableIntStateOf(3)
        private set
    val lowestKey: Int get() = (octave + 1) * 12

    /** The last key you played. Tapping an empty synth step puts this note there. */
    var lastNote by mutableIntStateOf(48)
        private set

    init {
        loadDemoPattern()
        sendEverythingToEngine()
    }

    fun togglePlaying() {
        isPlaying = !isPlaying
        NativeEngine.setPlaying(isPlaying)
    }

    fun changeTempo(bpm: Float) {
        tempo = bpm
        NativeEngine.setTempo(bpm)
    }

    fun changeSwing(amount: Float) {
        swing = amount
        NativeEngine.setSwing(amount)
    }

    fun selectTrack(track: Int) {
        selectedTrack = track
    }

    fun isStepOn(step: Int): Boolean =
        if (selectedTrack == SYNTH_TRACK) synthSteps[step] != NO_NOTE
        else drumSteps[selectedTrack][step]

    fun toggleStep(step: Int) {
        if (selectedTrack == SYNTH_TRACK) {
            val note = if (synthSteps[step] == NO_NOTE) lastNote else NO_NOTE
            synthSteps[step] = note
            NativeEngine.setSynthStep(step, note)
        } else {
            val on = !drumSteps[selectedTrack][step]
            drumSteps[selectedTrack][step] = on
            NativeEngine.setDrumStep(selectedTrack, step, on)
        }
    }

    fun drumPadPressed(track: Int) {
        NativeEngine.triggerDrum(track)
        selectedTrack = track
    }

    fun keyPressed(note: Int) {
        NativeEngine.synthNoteOn(note)
        lastNote = note
        selectedTrack = SYNTH_TRACK
    }

    fun keyReleased(note: Int) {
        NativeEngine.synthNoteOff(note)
    }

    fun shiftOctave(delta: Int) {
        octave = (octave + delta).coerceIn(1, 6)
    }

    fun changeSynthParam(param: Int, value: Float) {
        synthParams[param] = value
        NativeEngine.setSynthParam(param, value)
    }

    private fun loadDemoPattern() {
        for (step in 0 until STEPS step 4) drumSteps[0][step] = true   // kick on every beat
        drumSteps[1][4] = true                                        // snare on beats 2 and 4
        drumSteps[1][12] = true
        for (step in 2 until STEPS step 4) drumSteps[2][step] = true   // off-beat hats
        drumSteps[3][14] = true                                       // one clap

        val bassline = listOf(36, NO_NOTE, 36, 48, NO_NOTE, 36, NO_NOTE, 43,
                              36, NO_NOTE, 39, NO_NOTE, 36, 48, NO_NOTE, 46)
        bassline.forEachIndexed { step, note -> synthSteps[step] = note }
    }

    private fun sendEverythingToEngine() {
        NativeEngine.setPlaying(isPlaying)
        NativeEngine.setTempo(tempo)
        NativeEngine.setSwing(swing)
        for (track in 0 until DRUM_TRACKS) {
            for (step in 0 until STEPS) NativeEngine.setDrumStep(track, step, drumSteps[track][step])
        }
        for (step in 0 until STEPS) NativeEngine.setSynthStep(step, synthSteps[step])
        synthParams.forEachIndexed { param, value -> NativeEngine.setSynthParam(param, value) }
    }
}

private val NOTE_NAMES = listOf("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

/** 60 -> "C4", 61 -> "C#4" */
fun noteName(note: Int): String = NOTE_NAMES[note % 12] + (note / 12 - 1)

fun isBlackKey(note: Int): Boolean = NOTE_NAMES[note % 12].endsWith("#")
