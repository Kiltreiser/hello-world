package com.kiltreiser.stepsynth.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kiltreiser.stepsynth.StepSynthViewModel
import com.kiltreiser.stepsynth.SYNTH_TRACK
import com.kiltreiser.stepsynth.TRACK_NAMES
import com.kiltreiser.stepsynth.audio.NativeEngine
import com.kiltreiser.stepsynth.isBlackKey
import com.kiltreiser.stepsynth.noteName
import kotlin.math.roundToInt

private val PadShape = RoundedCornerShape(8.dp)

@Composable
fun StepSynthScreen(vm: StepSynthViewModel = viewModel()) {
    val playhead by rememberPlayhead()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        TransportSection(vm)
        TrackSelector(vm)
        StepGrid(vm, playhead)
        DrumPads(vm)
        Keyboard(vm)
        SynthControls(vm)
    }
}

/**
 * Asks the engine which step is playing, once per screen refresh, so the grid
 * can highlight it.
 */
@Composable
private fun rememberPlayhead(): State<Int> {
    val step = remember { mutableIntStateOf(-1) }
    LaunchedEffect(Unit) {
        while (true) {
            withFrameNanos { }
            step.intValue = NativeEngine.getCurrentStep()
        }
    }
    return step
}

@Composable
private fun TransportSection(vm: StepSynthViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "StepSynth",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.weight(1f),
            )
            Button(onClick = vm::togglePlaying, modifier = Modifier.width(120.dp)) {
                Text(if (vm.isPlaying) "■  Stop" else "▶  Play")
            }
        }
        LabeledSlider(
            label = "Tempo",
            valueText = "${vm.tempo.roundToInt()} BPM",
            value = vm.tempo,
            range = 60f..200f,
            onChange = { vm.changeTempo(it.roundToInt().toFloat()) },
        )
        LabeledSlider(
            label = "Swing",
            valueText = "${(50 + vm.swing * 50).roundToInt()}%",
            value = vm.swing,
            range = 0f..0.5f,
            onChange = vm::changeSwing,
        )
    }
}

@Composable
private fun TrackSelector(vm: StepSynthViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        TRACK_NAMES.forEachIndexed { track, name ->
            val selected = vm.selectedTrack == track
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .weight(1f)
                    .height(40.dp)
                    .clip(PadShape)
                    .background(if (selected) TrackColors[track] else MaterialTheme.colorScheme.surfaceVariant)
                    .clickable { vm.selectTrack(track) },
            ) {
                Text(
                    name,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = if (selected) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** 16 steps laid out 4 x 4. Tap a step to turn it on or off for the selected track. */
@Composable
private fun StepGrid(vm: StepSynthViewModel, playhead: Int) {
    val trackColor = TrackColors[vm.selectedTrack]
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in 0 until 4) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (col in 0 until 4) {
                    val step = row * 4 + col
                    val on = vm.isStepOn(step)
                    val label = if (vm.selectedTrack == SYNTH_TRACK && on) {
                        noteName(vm.synthSteps[step])
                    } else {
                        "${step + 1}"
                    }
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier
                            .weight(1f)
                            .aspectRatio(1f)
                            .clip(PadShape)
                            .background(if (on) trackColor else MaterialTheme.colorScheme.surface)
                            .then(
                                if (step == playhead) Modifier.border(3.dp, Color.White, PadShape)
                                else Modifier
                            )
                            .clickable { vm.toggleStep(step) },
                    ) {
                        Text(
                            label,
                            fontWeight = FontWeight.SemiBold,
                            color = if (on) Color.Black else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DrumPads(vm: StepSynthViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (track in 0 until NativeEngine.DRUM_TRACKS) {
            PlayPad(
                label = TRACK_NAMES[track],
                color = TrackColors[track],
                onDown = { vm.drumPadPressed(track) },
                modifier = Modifier
                    .weight(1f)
                    .height(64.dp),
            )
        }
    }
}

@Composable
private fun Keyboard(vm: StepSynthViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Keys  ${noteName(vm.lowestKey)}–${noteName(vm.lowestKey + 12)}",
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.weight(1f),
            )
            OutlinedButton(onClick = { vm.shiftOctave(-1) }) { Text("Oct −") }
            OutlinedButton(onClick = { vm.shiftOctave(1) }, modifier = Modifier.padding(start = 8.dp)) {
                Text("Oct +")
            }
        }
        // One octave plus the top C, drawn as a simple row of 13 keys.
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            for (i in 0..12) {
                val note = vm.lowestKey + i
                PlayPad(
                    label = noteName(note).dropLast(1),
                    color = if (isBlackKey(note)) Color(0xFF4D7A3A) else TrackColors[SYNTH_TRACK],
                    onDown = { vm.keyPressed(note) },
                    onUp = { vm.keyReleased(note) },
                    modifier = Modifier
                        .weight(1f)
                        .height(if (isBlackKey(note)) 80.dp else 110.dp),
                    fontSize = 10,
                )
            }
        }
    }
}

@Composable
private fun SynthControls(vm: StepSynthViewModel) {
    Column(
        verticalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(PadShape)
            .background(MaterialTheme.colorScheme.surface)
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Synth", color = MaterialTheme.colorScheme.onSurface, modifier = Modifier.weight(1f))
            val isSquare = vm.synthParams[NativeEngine.PARAM_WAVEFORM] >= 0.5f
            OutlinedButton(onClick = {
                vm.changeSynthParam(NativeEngine.PARAM_WAVEFORM, if (isSquare) 0f else 1f)
            }) {
                Text(if (isSquare) "Wave: Square" else "Wave: Saw")
            }
        }
        SynthSlider(vm, "Cutoff", NativeEngine.PARAM_CUTOFF)
        SynthSlider(vm, "Resonance", NativeEngine.PARAM_RESONANCE)
        SynthSlider(vm, "Env depth", NativeEngine.PARAM_ENV_AMOUNT)
        SynthSlider(vm, "Decay", NativeEngine.PARAM_DECAY)
    }
}

@Composable
private fun SynthSlider(vm: StepSynthViewModel, label: String, param: Int) {
    val value = vm.synthParams[param]
    LabeledSlider(
        label = label,
        valueText = "${(value * 100).roundToInt()}",
        value = value,
        range = 0f..1f,
        onChange = { vm.changeSynthParam(param, it) },
        color = TrackColors[SYNTH_TRACK],
    )
}

@Composable
private fun LabeledSlider(
    label: String,
    valueText: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    onChange: (Float) -> Unit,
    color: Color = MaterialTheme.colorScheme.primary,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            modifier = Modifier.width(96.dp),
        )
        Slider(
            value = value,
            onValueChange = onChange,
            valueRange = range,
            colors = SliderDefaults.colors(thumbColor = color, activeTrackColor = color),
            modifier = Modifier.weight(1f),
        )
        Text(
            valueText,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            modifier = Modifier
                .width(88.dp)
                .padding(start = 8.dp),
        )
    }
}

/**
 * A pad that makes sound the instant your finger touches it.
 *
 * A normal button (clickable) only reacts when you lift your finger, which
 * would feel laggy for an instrument, so this uses onPress instead.
 */
@Composable
private fun PlayPad(
    label: String,
    color: Color,
    onDown: () -> Unit,
    modifier: Modifier = Modifier,
    onUp: () -> Unit = {},
    fontSize: Int = 13,
) {
    var pressed by remember { mutableStateOf(false) }
    // pointerInput below is created once, so it must always read the latest callbacks.
    val currentOnDown by rememberUpdatedState(onDown)
    val currentOnUp by rememberUpdatedState(onUp)

    Box(
        contentAlignment = Alignment.BottomCenter,
        modifier = modifier
            .clip(PadShape)
            .background(if (pressed) color else color.copy(alpha = 0.35f))
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    pressed = true
                    currentOnDown()
                    // Remember the release action from the moment of pressing, so
                    // changing octave mid-press still releases the right note.
                    val release = currentOnUp
                    try {
                        tryAwaitRelease()
                    } finally {
                        // Runs even if the touch is cancelled (e.g. you start scrolling).
                        pressed = false
                        release()
                    }
                })
            }
            .padding(bottom = 6.dp),
    ) {
        Text(label, fontSize = fontSize.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
    }
}
