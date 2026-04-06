from faster_whisper import WhisperModel

model = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=4)
audio = r'C:\Users\Joseph\CodingAgent\MeetScribe\recordings\Test Meeting_6f5bf8a3\recording.wav'

for bs in [1, 2, 3, 5]:
    segments, info = model.transcribe(audio, beam_size=bs, language='en', vad_filter=False)
    segs = list(segments)
    text = ' '.join([s.text for s in segs])
    print(f'beam_size={bs}: {len(segs)} segs, text={text[:100]!r}')