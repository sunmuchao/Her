# Test Audio Files for Voice Transcription

This directory contains test audio files for voice transcription integration tests.

## Creating Test Audio Files

### Option 1: Use Browser Recording (Recommended)

1. Open browser console (F12)
2. Run the following code to record audio:

```javascript
// Start recording
async function recordTestAudio() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  const chunks = [];

  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    // Download the blob
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'test_zh.webm';
    a.click();
  };

  recorder.start();
  console.log('Recording started. Speak now: "测试语音识别文本"');

  // Stop after 3 seconds
  setTimeout(() => recorder.stop(), 3000);
}

recordTestAudio();
```

3. Save downloaded file as `test_zh.webm` in this directory

### Option 2: Use Python Script

Create a test audio file using pyaudio:

```python
import pyaudio
import wave

def record_test_audio(filename='test_zh.wav', duration=3):
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    print("* Recording. Speak: '测试语音识别文本'")
    frames = []

    for _ in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("* Done recording")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

record_test_audio('test_zh.wav')
```

## Test Audio Files

- `test_zh.webm` - Chinese test audio: "测试语音识别文本"
- `test_en.webm` - English test audio: "Test voice recognition"
- `test_silence.wav` - Silent audio (for error handling tests)

## Usage in Tests

```python
# In test files
test_audio_path = os.path.join(
    os.path.dirname(__file),
    'fixtures',
    'test_zh.webm'
)

with open(test_audio_path, 'rb') as f:
    audio_data = f.read()

# Send to Whisper API
result = _transcribe_audio(audio_data, language='zh')
```

## Notes

- WebM format is preferred (Chrome/Edge/Firefox support)
- WAV format is universal but larger
- Audio should be at least 2 seconds for reliable recognition
- Speak clearly in a quiet environment