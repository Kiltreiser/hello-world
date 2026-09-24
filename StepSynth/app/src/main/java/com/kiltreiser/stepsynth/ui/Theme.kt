package com.kiltreiser.stepsynth.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** One color per track: kick, snare, hat, clap, synth. */
val TrackColors = listOf(
    Color(0xFFFF7A1A),
    Color(0xFFFFC21A),
    Color(0xFF2EC5E8),
    Color(0xFFFF5C9A),
    Color(0xFF7ED957),
)

private val Colors = darkColorScheme(
    primary = Color(0xFFFF7A1A),
    onPrimary = Color(0xFF1A1A1A),
    background = Color(0xFF151515),
    onBackground = Color(0xFFEDEDED),
    surface = Color(0xFF232323),
    onSurface = Color(0xFFEDEDED),
    surfaceVariant = Color(0xFF2E2E2E),
    onSurfaceVariant = Color(0xFFB5B5B5),
)

@Composable
fun StepSynthTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, content = content)
}
