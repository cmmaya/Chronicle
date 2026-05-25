#!/usr/bin/env python3
"""
Simple audio loopback + capture test script for Chronicle.

What it does:
- Generates a 1s test tone (440Hz) and saves it to /tmp/sessions/test_tone.wav
- Attempts to record the microphone (via sounddevice) for the same duration and saves as WAV
- If PulseAudio/parec is available, attempts to record system audio (monitor source) and saves as WAV
- Plays the test tone through the default output while recording to make it easy to verify captures

Usage:
  python scripts/audio_test.py

Check output files in /tmp/sessions/chronicle_audio_test/

Notes:
- Requires sounddevice and numpy installed in the venv for microphone playback/recording
- Requires pulseaudio + pulseaudio-utils (parec) for system audio capture
"""
import os
import wave
import time
import logging
import subprocess
import threading
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

LOG = logging.getLogger('audio_test')
logging.basicConfig(level=logging.INFO)


def ensure_out_dir():
    # Prefer CHRONICLE_SESSIONS_DIR env var if set
    env_dir = os.environ.get('CHRONICLE_SESSIONS_DIR')
    if env_dir:
        out = Path(env_dir) / 'chronicle_audio_test'
        out.mkdir(parents=True, exist_ok=True)
        return out

    # Prefer repository 'sessions' folder if it exists or can be created
    script_root = Path(__file__).resolve().parents[1]
    repo_sessions = script_root / 'sessions'
    try:
        repo_sessions.mkdir(parents=True, exist_ok=True)
        out = repo_sessions / 'chronicle_audio_test'
        out.mkdir(parents=True, exist_ok=True)
        return out
    except Exception:
        # Fallback to /tmp
        out = Path('/tmp/sessions/chronicle_audio_test')
        out.mkdir(parents=True, exist_ok=True)
        return out


def generate_tone(filename: Path, duration: float = 1.0, sr: int = 44100, freq: float = 440.0):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * freq * t)
    # stereo
    stereo = np.column_stack([tone, tone]).astype(np.float32)
    # save as WAV (float32 -> we'll convert to int16 for portability)
    int16 = (stereo * 32767).astype(np.int16)
    with wave.open(str(filename), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int16.tobytes())
    LOG.info(f'Generated tone file: {filename}')


def record_microphone(out_path: Path, duration: float = 1.0, sr: int = 44100, channels: int = 2):
    if sd is None:
        raise RuntimeError('sounddevice not available')
    LOG.info('Starting microphone recording')
    data = sd.rec(int(duration * sr), samplerate=sr, channels=channels, dtype='float32')
    sd.wait()
    int16 = (data * 32767).astype(np.int16)
    with wave.open(str(out_path), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int16.tobytes())
    LOG.info(f'Microphone recording saved: {out_path}')


def list_pulse_monitor_sources():
    try:
        result = subprocess.run(['pactl', 'list', 'sources'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            LOG.warning('pactl failed: %s', result.stderr.strip())
            return []
        sources = []
        current = {}
        for line in result.stdout.splitlines():
            if line.startswith('Source #'):
                if current:
                    sources.append(current)
                current = {}
            elif line.strip().startswith('Name: '):
                current['name'] = line.split('Name: ')[1].strip()
            elif line.strip().startswith('Description: '):
                current['description'] = line.split('Description: ')[1].strip()
        if current:
            sources.append(current)
        monitors = [s for s in sources if s.get('description','').lower().startswith('monitor of')]
        return monitors
    except FileNotFoundError:
        LOG.warning('pactl not found')
        return []


def record_system_with_parec(out_path: Path, duration: float = 1.0, monitor_source: str = None):
    # Must have parec available
    try:
        subprocess.run(['parec', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError('parec not found')
    cmd = ['parec', '--format=s16le', '--rate=44100', '--channels=2']
    if monitor_source:
        cmd.append(f'--device={monitor_source}')
    LOG.info('Starting system recording with: %s', ' '.join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    time.sleep(duration)
    proc.terminate()
    raw = proc.communicate()[0]
    # write raw s16le as wav
    with wave.open(str(out_path), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(raw)
    LOG.info(f'System recording saved: {out_path}')


def play_tone_file(filename: Path):
    if sd is None:
        raise RuntimeError('sounddevice not available for playback')
    # read wav
    with wave.open(str(filename), 'rb') as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
        if wf.getnchannels() == 2:
            data = data.reshape(-1, 2)
    LOG.info('Playing tone')
    sd.play(data, sr)
    sd.wait()


def main():
    out_dir = ensure_out_dir()
    tone_file = out_dir / 'test_tone.wav'
    mic_file = out_dir / 'test_mic.wav'
    sys_file = out_dir / 'test_system.wav'

    duration = 1.0
    generate_tone(tone_file, duration=duration)

    # Check available pulse monitor sources
    monitors = list_pulse_monitor_sources()
    monitor_name = monitors[0]['name'] if monitors else None
    if monitor_name:
        LOG.info('Found monitor source: %s', monitor_name)
    else:
        LOG.info('No PulseAudio monitor source found; system capture will be skipped unless parec alone works')

    # Start system recording (if available)
    sys_thread = None
    sys_error = None
    try:
        if monitor_name:
            sys_thread = threading.Thread(target=record_system_with_parec, args=(sys_file, duration, monitor_name))
            sys_thread.start()
        else:
            # Try starting parec without specifying a device; maybe default works
            try:
                proc = subprocess.run(['parec', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                sys_thread = threading.Thread(target=record_system_with_parec, args=(sys_file, duration, None))
                sys_thread.start()
            except FileNotFoundError:
                LOG.info('parec not available; skipping system recording')
    except Exception as e:
        sys_error = e
        LOG.warning('System recording failed to start: %s', e)

    # Start microphone recording in separate thread
    mic_thread = threading.Thread(target=record_microphone, args=(mic_file, duration)) if sd is not None else None
    if mic_thread:
        mic_thread.start()
    else:
        LOG.info('sounddevice not available; skipping microphone recording')

    # Small delay to ensure recording processes are running, then play tone
    time.sleep(0.2)
    try:
        play_tone_file(tone_file)
    except Exception as e:
        LOG.warning('Playback failed: %s', e)

    # Wait for threads to finish
    if mic_thread:
        mic_thread.join()
    if sys_thread:
        sys_thread.join()

    LOG.info('Test complete. Check files in %s', out_dir)


if __name__ == '__main__':
    main()
