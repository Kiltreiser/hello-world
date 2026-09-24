package com.kiltreiser.stepsynth

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.kiltreiser.stepsynth.audio.NativeEngine
import com.kiltreiser.stepsynth.ui.StepSynthScreen
import com.kiltreiser.stepsynth.ui.StepSynthTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            StepSynthTheme {
                StepSynthScreen()
            }
        }
    }

    // Audio runs only while the app is on screen. It's released when you
    // switch away so other apps can use the audio hardware.
    override fun onResume() {
        super.onResume()
        if (!NativeEngine.start()) {
            Toast.makeText(this, "Couldn't start audio", Toast.LENGTH_LONG).show()
        }
    }

    override fun onPause() {
        NativeEngine.stop()
        super.onPause()
    }
}
