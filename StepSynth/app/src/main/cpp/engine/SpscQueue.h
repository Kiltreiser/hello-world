// A lock-free "single producer, single consumer" queue.
//
// The UI thread pushes events (like "play this note now") and the audio thread
// pops them. Neither side ever waits for the other, which matters because the
// audio thread must never block. Only ONE thread may push and only ONE may pop.
#pragma once

#include <array>
#include <atomic>
#include <cstddef>

template <typename T, size_t Capacity>
class SpscQueue {
public:
    // Returns false if the queue is full (the event is dropped).
    bool push(const T& item) {
        size_t tail = mTail.load(std::memory_order_relaxed);
        size_t next = (tail + 1) % Capacity;
        if (next == mHead.load(std::memory_order_acquire)) return false;
        mBuffer[tail] = item;
        mTail.store(next, std::memory_order_release);
        return true;
    }

    // Returns false if the queue is empty.
    bool pop(T& item) {
        size_t head = mHead.load(std::memory_order_relaxed);
        if (head == mTail.load(std::memory_order_acquire)) return false;
        item = mBuffer[head];
        mHead.store((head + 1) % Capacity, std::memory_order_release);
        return true;
    }

private:
    std::array<T, Capacity> mBuffer{};
    std::atomic<size_t> mHead{0};
    std::atomic<size_t> mTail{0};
};
