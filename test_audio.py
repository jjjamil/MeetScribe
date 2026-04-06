from faster_whisper import WhisperModel
import soundfile as sf
import numpy as np

model = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=4)

# Test audio
audio = r'C:\Users\Joseph\CodingAgent\MeetScribe\recordings\Final Test 1775470084_8820c5cc\recording.wav'
data, sr = sf.read(audio)
print(f'Raw: max={data.max():.4f}, mean={np.abs(data).mean():.4f}')

# Normalize audio to boost volume
data_norm = data / max(data.max(), abs(data.min())) * 0.9
data_norm = data_norm.astype(np.float32)

# Save normalized version for test
sf.write(audio.replace('.wav', '_norm.wav'), data_norm, sr)

# Try transcribing both
print('\\nOriginal:')
segs, info = model.transcribe(audio, beam_size=2, language='en', vad_filter=False)
segs = list(segs)
print(f'  {len(segs)} segments, duration={info.duration}')

print('\\nNormalized:')
segs2, info2 = model.transcribe(audio.replace('.wav', '_norm.wav'), beam_size=2, language='en', vad_filter=False)
segs2 = list(segs2)
print(f'  {len(segs2)} segments, duration={info2.duration}')
for s in segs2[:3]:
    print(f'  [{s.start:.1f}] {s.text}')