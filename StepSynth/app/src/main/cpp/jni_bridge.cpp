// JNI ("Java Native Interface") functions: the glue that lets the Kotlin code in
// audio/NativeEngine.kt call into C++. Each function name must match the Kotlin
// package, class and method name exactly:
//   Java_<package with _ instead of .>_<class>_<method>
#include <jni.h>

#include "OboePlayer.h"
#include "engine/AudioEngine.h"

namespace {
AudioEngine gEngine;
OboePlayer gPlayer(gEngine);
}  // namespace

#define JNI_METHOD(returnType, name) \
    extern "C" JNIEXPORT returnType JNICALL Java_com_kiltreiser_stepsynth_audio_NativeEngine_##name

JNI_METHOD(jboolean, start)(JNIEnv*, jobject) {
    return gPlayer.start() ? JNI_TRUE : JNI_FALSE;
}

JNI_METHOD(void, stop)(JNIEnv*, jobject) {
    gPlayer.stop();
}

JNI_METHOD(void, setPlaying)(JNIEnv*, jobject, jboolean playing) {
    gEngine.setPlaying(playing == JNI_TRUE);
}

JNI_METHOD(void, setTempo)(JNIEnv*, jobject, jfloat bpm) {
    gEngine.setTempo(bpm);
}

JNI_METHOD(void, setSwing)(JNIEnv*, jobject, jfloat amount) {
    gEngine.setSwing(amount);
}

JNI_METHOD(void, setDrumStep)(JNIEnv*, jobject, jint track, jint step, jboolean on) {
    gEngine.setDrumStep(track, step, on == JNI_TRUE);
}

JNI_METHOD(void, setSynthStep)(JNIEnv*, jobject, jint step, jint note) {
    gEngine.setSynthStep(step, note);
}

JNI_METHOD(void, setSynthParam)(JNIEnv*, jobject, jint param, jfloat value) {
    gEngine.setSynthParam(param, value);
}

JNI_METHOD(void, triggerDrum)(JNIEnv*, jobject, jint track) {
    gEngine.triggerDrum(track);
}

JNI_METHOD(void, synthNoteOn)(JNIEnv*, jobject, jint note) {
    gEngine.synthNoteOn(note);
}

JNI_METHOD(void, synthNoteOff)(JNIEnv*, jobject, jint note) {
    gEngine.synthNoteOff(note);
}

JNI_METHOD(jint, getCurrentStep)(JNIEnv*, jobject) {
    return gEngine.currentStep();
}
