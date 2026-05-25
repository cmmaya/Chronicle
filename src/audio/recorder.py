import sounddevice as sd
import numpy as np
import wave
from pathlib import Path
from datetime import datetime
import logging
import subprocess
from typing import List, Dict

logger = logging.getLogger(__name__)

class AudioRecorder:
    def __init__(self, session_path: str = '/tmp/sessions/session_001'):
        self.is_recording = False
        self.frames = []
        self.system_frames = []
        self.sample_rate = 44100
        self.channels = 2
        self.device_index = None  # System default
        self.start_time = None
        self.process = None
        self.system_stream = None
        self.session_path = Path(session_path)
        self.audio_path = self.session_path / 'audio'
        self.audio_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list_monitor_sources() -> List[Dict[str, str]]:
        """List available PulseAudio monitor sources.
        Returns:
            List of dicts with 'name' and 'description' of each monitor source
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sources'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f'pactl failed: {result.stderr}')

            sources = []
            current_source = {}
            for line in result.stdout.splitlines():
                if line.startswith('Source #'):
                    if current_source:
                        sources.append(current_source)
                    current_source = {}
                elif line.strip().startswith('Name: '):
                    current_source['name'] = line.split('Name: ')[1].strip()
                elif line.strip().startswith('Description: '):
                    current_source['description'] = line.split('Description: ')[1].strip()

            if current_source:
                sources.append(current_source)

            # Filter for monitor sources
            return [
                s for s in sources
                if s.get('description', '').lower().startswith('monitor of')
            ]

        except Exception as e:
            logger.error(f'Failed to list monitor sources: {str(e)}')
            return []

    def get_start_time(self) -> datetime:
        """Get the recording start time for timestamp synchronization.
        
        Returns:
            datetime object representing when recording started,
            or None if recording has not been started.
        """
        return self.start_time

    def get_elapsed_time(self) -> float:
        """Get elapsed time since recording started in seconds.
        
        Returns:
            Float representing seconds since recording started,
            or 0.0 if not currently recording.
        """
        if not self.is_recording or not self.start_time:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()

    def _validate_audio_data(self):
        if not self.frames:
            raise ValueError('No audio frames captured')
        total_samples = sum(len(frame) for frame in self.frames)
        if total_samples == 0:
            raise ValueError('Empty audio frames captured')

    def start_recording(self, device_index: int = None, monitor: bool = False, monitor_source: str = None, mic: bool = True, system_device_index: int = None):
        if self.is_recording:
            return

        self.device_index = device_index
        self.frames = []
        self.is_recording = True
        self.start_time = datetime.now()

        if monitor:
            # Verify parec is available
            try:
                subprocess.run(['parec', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                # parec not available - log and continue. On Windows/other platforms system capture
                # may be handled via a loopback input device (handled below using sounddevice)
                logger.warning('parec not found. System audio capture via parec unavailable')
                self.process = None

            # Use specified monitor source or default
            if monitor_source is None:
                sources = self.list_monitor_sources()
                if not sources:
                    logger.warning('No PulseAudio monitor sources found')
                else:
                    monitor_source = sources[0]['name']

            if self.process is None and monitor_source is not None:
                try:
                    self.process = subprocess.Popen(
                        ['parec', '--format=s16le', '--rate=44100', '--channels=2', f'--device={monitor_source}'],
                        stdout=subprocess.PIPE
                    )
                    logger.info(f'System audio recording started using parec (source: {monitor_source})')
                except Exception as e:
                    logger.warning(f'Failed to start parec process: {e}')
                    self.process = None

            # If parec wasn't started, try to start system capture via a provided device index
            if self.process is None:
                try:
                    import sounddevice as sd
                    devices = sd.query_devices()
                    loopback_index = None
                    # If a system_device_index was provided, prefer it
                    if system_device_index is not None:
                        # validate index
                        if 0 <= int(system_device_index) < len(devices):
                            loopback_index = int(system_device_index)
                    else:
                        for idx, dev in enumerate(devices):
                            name = str(dev.get('name', '')).lower()
                            if 'loopback' in name or 'stereo mix' in name or 'wave out' in name:
                                loopback_index = idx
                                break

                    if loopback_index is not None:
                        def sys_callback(indata, frames, time, status):
                            if self.is_recording:
                                self.system_frames.append(indata.copy())

                        self.system_stream = sd.InputStream(
                            samplerate=self.sample_rate,
                            channels=self.channels,
                            device=loopback_index,
                            dtype='float32',
                            callback=sys_callback
                        )
                        self.system_stream.start()
                        logger.info(f'System audio recording started on loopback device index {loopback_index}')
                    else:
                        logger.warning('No loopback/stereo-mix device found for system capture')
                except Exception as e:
                    logger.warning(f'Could not start system audio via sounddevice: {e}')

        def callback(indata, frames, time, status):
            if self.is_recording:
                self.frames.append(indata.copy())

        try:
            if mic:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    device=self.device_index,
                    dtype='float32',
                    callback=callback
                )
                self.stream.start()
                logger.info(f'Microphone recording started on device {self.device_index}')
            else:
                logger.info('Microphone recording skipped (mic=False)')
        except Exception as e:
            logger.error(f'Failed to start recording: {str(e)}')
            raise

    def stop_recording(self, label: str = 'recording'):
        if not self.is_recording:
            return None

        self.is_recording = False
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_paths = []

        # Handle system audio first (parec raw or system_frames)
        if self.process:
            try:
                self.process.terminate()
                raw_audio = self.process.communicate()[0]
                bytes_data = raw_audio
                system_path = self.audio_path / f'{timestamp}_{label}_system.wav'
                with wave.open(str(system_path), 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(bytes_data)
                output_paths.append(str(system_path))
                logger.info(f'Saved system recording to {system_path}')
            except Exception as e:
                logger.error(f'Failed to save system recording: {e}')
            finally:
                self.process = None
        elif getattr(self, 'system_frames', None):
            try:
                if getattr(self, 'system_stream', None):
                    try:
                        self.system_stream.stop()
                        self.system_stream.close()
                    except Exception:
                        pass
                if self.system_frames:
                    sys_audio = np.concatenate(self.system_frames, axis=0)
                    int16_sys = (sys_audio * 32767).astype(np.int16)
                    system_path = self.audio_path / f'{timestamp}_{label}_system.wav'
                    with wave.open(str(system_path), 'wb') as wf:
                        wf.setnchannels(self.channels)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes(int16_sys.tobytes())
                    output_paths.append(str(system_path))
                    logger.info(f'Saved system recording to {system_path}')
            except Exception as e:
                logger.error(f'Failed to save system recording from frames: {e}')

        # Handle microphone audio
        try:
            if getattr(self, 'stream', None):
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass

            if self.frames:
                audio_data = np.concatenate(self.frames, axis=0)
                int16 = (audio_data * 32767).astype(np.int16)
                mic_path = self.audio_path / f'{timestamp}_{label}.wav'
                with wave.open(str(mic_path), 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(int16.tobytes())
                output_paths.append(str(mic_path))
                logger.info(f'Saved microphone recording to {mic_path}')
        except Exception as e:
            logger.error(f'Failed to save microphone recording: {str(e)}')

        # Reset frames
        self.frames = []
        self.system_frames = []

        return output_paths
