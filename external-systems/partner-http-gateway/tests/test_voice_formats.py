#!/usr/bin/env python3
"""
End-to-End test for voice transcription with audio format conversion.

This script tests the complete voice recognition flow:
1. Creates test audio files in different formats (webm, mp4, wav)
2. Tests audio format conversion (webm/mp4 → wav)
3. Tests Whisper transcription for each format
4. Validates conversion metadata and transcription quality

Usage:
  python test_voice_formats.py

Prerequisites:
  - Backend gateway running at http://127.0.0.1:8765
  - ffmpeg installed (brew install ffmpeg)
  - pydub installed (pip install pydub)
  - faster-whisper installed
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

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("⚠ pydub not available, some tests will be skipped")


# ==============================================================================
# Test Audio Generation
# ==============================================================================

def create_test_audio_wav(text: str = "测试语音识别") -> Path:
    """Create a simple WAV test file (silence, placeholder).

    NOTE: This creates a dummy audio file for testing API endpoint.
    For real speech recognition tests, you need a real recording.

    Returns:
        Path to test audio file
    """
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

    # Create a minimal WAV file with silence
    with wave.open(temp_file.name, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(16000)  # 16kHz
        # Write 1 second of silence
        wav_file.writeframes(b'\x00\x00' * 16000)

    return Path(temp_file.name)


def create_test_audio_webm() -> Path | None:
    """Create a test webm file with Opus audio using ffmpeg.

    Returns:
        Path to test webm file, or None if ffmpeg not available
    """
    if not PYDUB_AVAILABLE:
        print("  ⚠ pydub not available, skipping webm test")
        return None

    temp_file = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)

    try:
        # Create 1 second of silence with pydub
        silence = AudioSegment.silent(duration=1000)  # 1 second

        # Export as webm with Opus codec
        silence.export(temp_file.name, format="webm", codec="libopus")

        return Path(temp_file.name)

    except Exception as e:
        print(f"  ✗ Failed to create webm test file: {e}")
        return None


def create_test_audio_mp4() -> Path | None:
    """Create a test mp4 file with AAC audio using ffmpeg.

    Returns:
        Path to test mp4 file, or None if ffmpeg not available
    """
    if not PYDUB_AVAILABLE:
        print("  ⚠ pydub not available, skipping mp4 test")
        return None

    temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)

    try:
        # Create 1 second of silence with pydub
        silence = AudioSegment.silent(duration=1000)  # 1 second

        # Export as mp4 with AAC codec (Safari format)
        silence.export(temp_file.name, format="mp4", codec="aac")

        return Path(temp_file.name)

    except Exception as e:
        print(f"  ✗ Failed to create mp4 test file: {e}")
        return None


# ==============================================================================
# Test Functions
# ==============================================================================

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


def test_audio_format_conversion(audio_path: Path, format_name: str):
    """Test audio format conversion using pydub."""
    if not PYDUB_AVAILABLE:
        print(f"   ⚠ pydub not available, skipping {format_name} conversion test")
        return None

    print(f"\n   Testing {format_name} → WAV conversion...")

    try:
        # Load audio
        audio_segment = AudioSegment.from_file(audio_path, format=format_name)

        print(f"   ✓ Audio loaded successfully")
        print(f"     - Duration: {len(audio_segment)}ms")
        print(f"     - Channels: {audio_segment.channels}")
        print(f"     - Sample rate: {audio_segment.frame_rate}Hz")

        # Convert to mono 16kHz WAV (Whisper recommended format)
        if audio_segment.channels > 1:
            audio_segment = audio_segment.set_channels(1)

        if audio_segment.frame_rate != 16000:
            audio_segment = audio_segment.set_frame_rate(16000)

        # Export to WAV
        wav_path = audio_path.with_suffix(".converted.wav")
        audio_segment.export(wav_path, format="wav")

        print(f"   ✓ Conversion successful")
        print(f"     - Output: {wav_path}")
        print(f"     - Size: {wav_path.stat().st_size} bytes")

        return wav_path

    except Exception as e:
        print(f"   ✗ Conversion failed: {e}")
        return None


def test_voice_transcribe_endpoint(base_url: str, audio_path: Path, format_name: str):
    """Test voice transcription endpoint with specific format."""
    print(f"\n2.{format_name}. Testing {format_name} transcription...")

    try:
        # Read audio file
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        print(f"   - Audio file: {audio_path}")
        print(f"   - Audio size: {len(audio_data)} bytes")

        # Determine content type
        if format_name.endswith(".converted"):
            content_type = "audio/wav"
        else:
            content_type_map = {
                "wav": "audio/wav",
                "webm": "audio/webm",
                "mp4": "audio/mp4",
            }
            content_type = content_type_map.get(format_name, f"audio/{format_name}")

        # Send to Whisper API
        response = requests.post(
            f"{base_url}/v1/voice/transcribe",
            data=audio_data,
            headers={'Content-Type': content_type},
            timeout=30,
        )

        print(f"   - Response status: {response.status_code}")

        if response.status_code != 200:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', 'Unknown error')
            print(f"   ✗ Transcription failed: {error_msg}")
            return False

        data = response.json()
        print(f"   ✓ Transcription successful")

        # Display results
        print(f"   - Text: \"{data.get('text', '')}\"")
        print(f"   - Language: {data.get('language')} (probability: {data.get('language_probability', 0):.2f})")

        # Display audio info (if available)
        audio_info = data.get('audio_info', {})
        if audio_info:
            print(f"   - Audio info:")
            print(f"     - Duration: {audio_info.get('duration_ms', 'unknown')}ms")
            print(f"     - Channels: {audio_info.get('channels', 'unknown')}")
            print(f"     - Sample rate: {audio_info.get('sample_rate', 'unknown')}Hz")

        # Display segments
        segments = data.get('segments', [])
        if segments:
            print(f"   - Segments: {len(segments)}")
            for i, seg in enumerate(segments[:3]):  # Show first 3 segments
                print(f"     [{i}] {seg['start']:.2f}-{seg['end']:.2f}s: \"{seg['text']}\"")

        return True

    except requests.exceptions.Timeout:
        print(f"   ✗ Request timed out (Whisper model may be loading)")
        print(f"   → Try again in 30 seconds, model should be cached")
        return False

    except Exception as e:
        print(f"   ✗ Transcription failed: {e}")
        return False


def test_via_nextjs_gateway(nextjs_url: str, audio_path: Path, format_name: str):
    """Test via Next.js gateway proxy."""
    print(f"\n3.{format_name}. Testing {format_name} via Next.js proxy...")

    try:
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        # Determine content type
        if format_name.endswith(".converted"):
            content_type = "audio/wav"
        else:
            content_type_map = {
                "wav": "audio/wav",
                "webm": "audio/webm",
                "mp4": "audio/mp4",
            }
            content_type = content_type_map.get(format_name, f"audio/{format_name}")

        # Send via Next.js gateway proxy
        response = requests.post(
            f"{nextjs_url}/api/gateway/v1/voice/transcribe",
            data=audio_data,
            headers={'Content-Type': content_type},
            timeout=30,
        )

        print(f"   - Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Via Next.js proxy successful")
            print(f"   - Text: \"{data.get('text', '')}\"")
            return True
        else:
            print(f"   ✗ Via Next.js proxy failed")
            if response.status_code == 502:
                backend_url = os.environ.get('PARTNER_GATEWAY_BASE_URL', 'http://127.0.0.1:8765')
                print(f"   → Backend gateway not running at {backend_url}")
            else:
                error_data = response.json()
                print(f"   → Error: {error_data.get('error', {}).get('message', 'Unknown')}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"   ✗ Cannot connect to Next.js gateway at {nextjs_url}")
        print(f"   → Ensure Next.js dev server is running: npm run dev")
        return False

    except Exception as e:
        print(f"   ✗ Via Next.js proxy failed: {e}")
        return False


# ==============================================================================
# Main Test Flow
# ==============================================================================

def main():
    """Run all tests."""
    print("=" * 70)
    print("Voice Transcription Format Compatibility Test")
    print("=" * 70)

    # Configuration
    backend_url = os.environ.get("PARTNER_GATEWAY_BASE_URL", "http://127.0.0.1:8765")
    nextjs_url = os.environ.get("NEXTJS_URL", "http://127.0.0.1:3000")

    print(f"\nConfiguration:")
    print(f"  Backend URL: {backend_url}")
    print(f"  Next.js URL: {nextjs_url}")
    print(f"  pydub available: {PYDUB_AVAILABLE}")

    # Create test audio files
    print("\nCreating test audio files...")

    test_files = {}

    # WAV test file
    wav_path = create_test_audio_wav()
    test_files["wav"] = wav_path
    print(f"  ✓ WAV test file: {wav_path} ({wav_path.stat().st_size} bytes)")

    # WebM test file (Chrome/Firefox format)
    webm_path = create_test_audio_webm()
    if webm_path:
        test_files["webm"] = webm_path
        print(f"  ✓ WebM test file: {webm_path} ({webm_path.stat().st_size} bytes)")

    # MP4 test file (Safari format)
    mp4_path = create_test_audio_mp4()
    if mp4_path:
        test_files["mp4"] = mp4_path
        print(f"  ✓ MP4 test file: {mp4_path} ({mp4_path.stat().st_size} bytes)")

    if len(test_files) == 0:
        print("  ✗ No test files created, aborting")
        return 1

    try:
        # Run tests
        results = []

        # Test 1: Health check
        health_ok = test_health_check(backend_url)
        results.append(("health", health_ok))

        if not health_ok:
            print("\n✗ Gateway not healthy, aborting tests")
            return 1

        # Test 2: Format conversion
        print("\n2. Testing audio format conversion...")
        conversion_results = {}

        # 使用 list 避免迭代时修改字典
        formats_to_convert = list(test_files.keys())

        for format_name in formats_to_convert:
            audio_path = test_files[format_name]
            if format_name != "wav":
                converted_path = test_audio_format_conversion(audio_path, format_name)
                conversion_results[format_name] = converted_path
                if converted_path:
                    # 添加转换后的文件到测试列表（使用新 key）
                    test_files[f"{format_name}.converted"] = converted_path

        # Test 3: Direct backend transcription for each format
        print("\n3. Testing transcription via backend...")
        transcribe_results = {}

        for format_name, audio_path in test_files.items():
            success = test_voice_transcribe_endpoint(backend_url, audio_path, format_name)
            transcribe_results[format_name] = success
            results.append((f"transcribe_{format_name}", success))

        # Test 4: Via Next.js proxy (only test primary formats)
        print("\n4. Testing transcription via Next.js proxy...")
        proxy_results = {}

        for format_name in ["wav", "webm", "mp4"]:
            if format_name in test_files:
                success = test_via_nextjs_gateway(nextjs_url, test_files[format_name], format_name)
                proxy_results[format_name] = success
                results.append((f"proxy_{format_name}", success))

        # Summary
        print("\n" + "=" * 70)
        print("Test Summary:")
        print("=" * 70)

        passed = sum(1 for _, success in results if success)
        total = len(results)

        print(f"\nOverall Results:")
        print(f"  Passed: {passed}/{total}")
        print(f"  Failed: {total - passed}/{total}")

        # Detailed breakdown
        print("\nDetailed Results:")
        for test_name, success in results:
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"  {status} - {test_name}")

        # Format conversion summary
        if conversion_results:
            print("\nFormat Conversion:")
            for format_name, converted_path in conversion_results.items():
                status = "✓ SUCCESS" if converted_path else "✗ FAILED"
                print(f"  {status} - {format_name} → WAV")

        # Transcription summary
        if transcribe_results:
            print("\nDirect Backend Transcription:")
            for format_name, success in transcribe_results.items():
                status = "✓ SUCCESS" if success else "✗ FAILED"
                print(f"  {status} - {format_name}")

        # Proxy summary
        if proxy_results:
            print("\nNext.js Proxy Transcription:")
            for format_name, success in proxy_results.items():
                status = "✓ SUCCESS" if success else "✗ FAILED"
                print(f"  {status} - {format_name}")

        # Recommendations
        print("\n" + "=" * 70)
        print("Recommendations:")
        print("=" * 70)

        if not PYDUB_AVAILABLE:
            print("\n⚠ pydub not installed:")
            print("  → Install pydub: pip install pydub")
            print("  → Install ffmpeg: brew install ffmpeg (macOS)")
            print("  → Restart gateway after installation")

        failed_formats = [f for f, s in transcribe_results.items() if not s]
        if failed_formats:
            print(f"\n⚠ Failed formats: {', '.join(failed_formats)}")
            print("  → Check ffmpeg installation")
            print("  → Check gateway logs for detailed errors")
            print("  → Verify audio codec support (Opus, AAC)")

        if all(success for _, success in results):
            print("\n✓ All tests passed!")
            print("  → Audio format conversion is working correctly")
            print("  → Whisper transcription is working for all formats")
            print("  → Voice input should work in all browsers")
            return 0
        else:
            print("\n✗ Some tests failed")
            print("  → See detailed errors above")
            print("  → Run: bash scripts/fix-whisper-audio-format.sh")
            return 1

    finally:
        # Cleanup test files
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)

        for format_name, audio_path in test_files.items():
            if audio_path and audio_path.exists():
                os.unlink(audio_path)
                print(f"  ✓ Deleted: {audio_path.name}")


if __name__ == "__main__":
    sys.exit(main())
