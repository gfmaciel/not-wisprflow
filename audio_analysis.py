from __future__ import annotations

import math
from array import array

SAMPLE_RATE = 16000
_BAND_RANGES = (
    (80.0, 250.0),
    (250.0, 500.0),
    (500.0, 1000.0),
    (1000.0, 2000.0),
    (2000.0, 6000.0),
)


def analyze_mic_frame(frame: bytes, sample_rate: int = SAMPLE_RATE) -> tuple[float, ...]:
    """
    Convert a PCM frame into a symmetric 9-element energy profile.

    The values are derived from FFT band energy and scaled by the frame loudness
    so silence decays to dots while speech lifts the center bars first.
    """

    samples = array("h")
    samples.frombytes(frame)
    if not samples:
        return (0.0,) * 9

    floats = [sample / 32768.0 for sample in samples]
    rms = math.sqrt(sum(sample * sample for sample in floats) / len(floats))
    if rms < 0.001:
        return (0.0,) * 9

    windowed = _apply_hann_window(floats)
    spectrum = _fft(windowed)
    magnitudes = [abs(value) for value in spectrum[: len(windowed) // 2]]

    band_values = [
        _band_energy(magnitudes, sample_rate, len(windowed), low, high)
        for low, high in _BAND_RANGES
    ]
    peak = max(band_values) or 1.0
    presence = min(1.0, rms * 40.0)
    normalized = [min(1.0, ((value / peak) ** 0.85) * presence) for value in band_values]

    # Mirror low->high frequencies around the center so the notch reads as a
    # symmetric capture indicator rather than a scrolling history waveform.
    return (
        normalized[4],
        normalized[3],
        normalized[2],
        normalized[1],
        normalized[0],
        normalized[1],
        normalized[2],
        normalized[3],
        normalized[4],
    )


def _apply_hann_window(samples: list[float]) -> list[float]:
    if len(samples) == 1:
        return samples[:]

    n = 1 << (len(samples) - 1).bit_length()
    n = max(512, n)

    windowed = [
        sample * (0.5 - 0.5 * math.cos((2.0 * math.pi * idx) / (len(samples) - 1)))
        for idx, sample in enumerate(samples)
    ]
    windowed.extend([0.0] * (n - len(windowed)))
    return windowed


def _fft(values: list[float]) -> list[complex]:
    n = len(values)
    data = [complex(value, 0.0) for value in values]

    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            data[i], data[j] = data[j], data[i]

    length = 2
    while length <= n:
        angle = -2.0 * math.pi / length
        wlen = complex(math.cos(angle), math.sin(angle))
        half = length // 2
        for start in range(0, n, length):
            w = 1.0 + 0.0j
            for i in range(start, start + half):
                u = data[i]
                v = data[i + half] * w
                data[i] = u + v
                data[i + half] = u - v
                w *= wlen
        length <<= 1

    return data


def _band_energy(
    magnitudes: list[float],
    sample_rate: int,
    fft_size: int,
    low_hz: float,
    high_hz: float,
) -> float:
    lo = max(1, int(low_hz * fft_size / sample_rate))
    hi = min(len(magnitudes), int(high_hz * fft_size / sample_rate) + 1)
    if hi <= lo:
        return 0.0
    window = magnitudes[lo:hi]
    return sum(window) / len(window)
