#!/usr/bin/env python3
"""
Quick test for WAV format (no conversion needed).

Usage:
  python test_wav_quick.py
"""

import tempfile
import wave
import sys

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests


def create_test_wav():
    """Create a test WAV file with silence."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

    with wave.open(temp_file.name, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b'\x00\x00' * 16000)

    return temp_file.name


def test_quick():
    """Quick test for WAV format."""
    print("=" * 70)
    print("Quick WAV Test (No Conversion Needed)")
    print("=" * 70)

    # Create test WAV
    wav_path = create_test_wav()
    print(f"\n✓ Created test WAV: {wav_path}")

    try:
        # Test backend directly
        backend_url = "http://127.0.0.1:8765"

        print(f"\n1. Testing health check...")
        try:
            response = requests.get(f"{backend_url}/health", timeout=5)
            if response.status_code == 200:
                print("   ✓ Gateway is healthy")
            else:
                print(f"   ✗ Gateway health check failed: {response.status_code}")
                return 1
        except Exception as e:
            print(f"   ✗ Cannot connect to gateway: {e}")
            print("   → Start gateway: python -m gateway")
            return 1

        # Test transcription
        print(f"\n2. Testing WAV transcription...")
        with open(wav_path, 'rb') as f:
            audio_data = f.read()

        response = requests.post(
            f"{backend_url}/v1/voice/transcribe",
            data=audio_data,
            headers={'Content-Type': 'audio/wav'},
            timeout=30,
        )

        print(f"   - Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Transcription successful")
            print(f"   - Text: \"{data.get('text', '')}\"")
            print(f"   - Language: {data.get('language')} (prob: {data.get('language_probability', 0):.2f})")

            # Check audio_info
            audio_info = data.get('audio_info', {})
            if audio_info:
                print(f"   - Audio info:")
                for key, value in audio_info.items():
                    print(f"     - {key}: {value}")

            print("\n✓ WAV format works! (No conversion needed)")
            return 0
        else:
            error_data = response.json()
            print(f"   ✗ Transcription failed: {error_data.get('error', {}).get('message')}")
            return 1

    finally:
        # Cleanup
        import os
        if os.path.exists(wav_path):
            os.unlink(wav_path)
            print(f"\n✓ Cleaned up: {wav_path}")


if __name__ == "__main__":
    sys.exit(test_quick())