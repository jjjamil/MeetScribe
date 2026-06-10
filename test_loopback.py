import soundcard as sc
import numpy as np

print("All speakers:")
for s in sc.all_speakers():
    print(" ", s.name)

print()
print("All microphones (including loopback):")
for m in sc.all_microphones(include_loopback=True):
    print(" ", m.name)

print()
print("Trying to open default speaker as loopback recorder...")
try:
    default_spk = sc.default_speaker()
    loopback_mic = sc.get_microphone(default_spk.id, include_loopback=True)
    print("Got loopback mic:", loopback_mic.name)
    with loopback_mic.recorder(samplerate=16000, channels=1) as rec:
        data = rec.record(numframes=16000)  # 1 second
    print("Captured", len(data), "samples, peak:", round(float(np.max(np.abs(data))), 4))
except Exception as e:
    print("Failed:", e)
