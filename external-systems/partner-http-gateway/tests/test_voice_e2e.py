#!/usr/bin/env python3
"""
End-to-End test for voice transcription flow.

This script tests the complete voice recognition flow:
1. Simulates recording audio (or uses a test audio file)
2. Sends audio to backend Whisper API
3. Verifies transcription result

Usage:
  python test_voice_e2e.py

Prerequisites:
  - Backend gateway running at http://127.0.0.1:8765
  - Faster-Whisper installed
"""

import io
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests


def create_test_audio_file(text: str = "测试语音识别") -> Path:
    """Create a simple test audio file (sine wave, not actual speech).

    NOTE: This creates a dummy audio file for testing API endpoint.
    For real speech recognition tests, you need a real recording.

    Returns:
        Path to test audio file
    """
    # Create a simple WAV file with silence (placeholder)
    # In production, you'd use a real audio recording
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

    # Create a minimal WAV file
    with wave.open(temp_file.name, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(16000)  # 16kHz
        # Write 1 second of silence (zeros)
        wav_file.writeframes(b'\x00\x00' * 16000)

    return Path(temp_file.name)


def test_health_check(base_url: str):
    """Test gateway health endpoint."""
    print("1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
        data = response.json()

        print(f"   ✓ Gateway is healthy")
        print(f"   - Surface: {data.get('surface')}")
        print(f"   - Services: {data.get('services')}")
        return True
    except Exception as e:
        print(f"   ✗ Health check failed: {e}")
        return False


def test_voice_transcribe_endpoint(base_url: str, audio_path: Path):
    """Test voice transcription endpoint."""
    print("\n2. Testing voice transcription...")

    try:
        # Read audio file
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        print(f"   - Audio file: {audio_path}")
        print(f"   - Audio size: {len(audio_data)} bytes")

        # Send to Whisper API
        response = requests.post(
            f"{base_url}/v1/voice/transcribe",
            data=audio_data,
            headers={'Content-Type': 'audio/wav'},
            timeout=30,  # Whisper may take time on first run
        )

        print(f"   - Response status: {response.status_code}")

        if response.status_code != 200:
            error_data = response.json()
            print(f"   ✗ Transcription failed: {error_data.get('error', {}).get('message')}")
            return False

        data = response.json()
        print(f"   ✓ Transcription successful")
        print(f"   - Text: {data.get('text')}")
        print(f"   - Language: {data.get('language')} (probability: {data.get('language_probability'):.2f})")
        print(f"   - Segments: {len(data.get('segments', []))}")

        return True

    except requests.exceptions.Timeout:
        print(f"   ✗ Request timed out (Whisper model may be loading)")
        print(f"   → Try again in 30 seconds, model should be cached")
        return False

    except Exception as e:
        print(f"   ✗ Transcription failed: {e}")
        return False


def test_via_nextjs_gateway(nextjs_url: str, audio_path: Path):
    """Test via Next.js gateway proxy."""
    print("\n3. Testing via Next.js gateway proxy...")

    try:
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        # Send via Next.js gateway proxy
        response = requests.post(
            f"{nextjs_url}/api/gateway/v1/voice/transcribe",
            data=audio_data,
            headers={'Content-Type': 'audio/wav'},
            timeout=30,
        )

        print(f"   - Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Via Next.js proxy successful")
            print(f"   - Text: {data.get('text')}")
            return True
        else:
            print(f"   ✗ Via Next.js proxy failed")
            if response.status_code == 502:
                print(f"   → Backend gateway not running at {os.environ.get('PARTNER_GATEWAY_BASE_URL', 'http://127.0.0.1:8765')}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"   ✗ Cannot connect to Next.js gateway at {nextjs_url}")
        print(f"   → Ensure Next.js dev server is running: npm run dev")
        return False

    except Exception as e:
        print(f"   ✗ Via Next.js proxy failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("Voice Transcription End-to-End Test")
    print("=" * 70)

    # Configuration
    backend_url = os.environ.get("PARTNER_GATEWAY_BASE_URL", "http://127.0.0.1:8765")
    nextjs_url = os.environ.get("NEXTJS_URL", "http://localhost:3000")

    print(f"\nConfiguration:")
    print(f"  Backend URL: {backend_url}")
    print(f"  Next.js URL: {nextjs_url}")

    # Create test audio file
    print("\nCreating test audio file...")
    audio_path = create_test_audio_file()
    print(f"  ✓ Test audio created: {audio_path}")

    try:
        # Run tests
        results = []

        # Test 1: Health check
        results.append(test_health_check(backend_url))

        # Test 2: Direct backend API
        if results[0]:  # Only if health check passed
            results.append(test_voice_transcribe_endpoint(backend_url, audio_path))

        # Test 3: Via Next.js proxy
        results.append(test_via_nextjs_gateway(nextjs_url, audio_path))

        # Summary
        print("\n" + "=" * 70)
        print("Test Summary:")
        print(f"  Passed: {sum(results)}/{len(results)}")
        print(f"  Failed: {len(results) - sum(results)}/{len(results)}")

        if all(results):
            print("\n✓ All tests passed!")
            return 0
        else:
            print("\n✗ Some tests failed. See errors above.")
            return 1

    finally:
        # Cleanup test audio file
        if audio_path.exists():
            os.unlink(audio_path)
            print(f"\nCleaned up test file: {audio_path}")


if __name__ == "__main__":
    sys.exit(main())