from PySide6.QtWidgets import QApplication
from src.app.window import MainWindow
import subprocess
import logging
import time

from src.audio.recorder import AudioRecorder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_pulseaudio():
    """Start PulseAudio if not running."""
    try:
        result = subprocess.run(
            ['pulseaudio', '--check'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.info("Starting PulseAudio...")
            subprocess.Popen(
                ['pulseaudio', '--start'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            logger.info("PulseAudio is already running")
    except FileNotFoundError:
        logger.warning("PulseAudio not installed - system audio recording will be disabled")


def run_audio_self_test():
    """Run a quick self-test for microphone and system audio.

    - Microphone: start a 1s recording via sounddevice
    - System: check for PulseAudio monitor sources and try a 1s capture via parec
    Logs results and returns a dict with statuses.
    """
    results = {
        'microphone': {'ok': False, 'message': ''},
        'system': {'ok': False, 'message': ''}
    }

    recorder = AudioRecorder(session_path='/tmp/sessions/selftest')

    # Microphone test
    try:
        logger.info('Starting microphone self-test (1s)')
        recorder.start_recording(monitor=False)
        time.sleep(1.0)
        recorder.stop_recording(label='selftest_mic')
        results['microphone']['ok'] = True
        results['microphone']['message'] = 'Microphone recording succeeded'
        logger.info('Microphone self-test succeeded')
    except Exception as e:
        results['microphone']['message'] = f'Microphone test failed: {e}'
        logger.warning(results['microphone']['message'])

    # System audio test (PulseAudio)
    try:
        sources = recorder.list_monitor_sources()
        if not sources:
            results['system']['message'] = 'No PulseAudio monitor sources found'
            logger.warning(results['system']['message'])
        else:
            monitor_source = sources[0]['name']
            logger.info(f'Starting system audio self-test (1s) using source: {monitor_source}')
            recorder.start_recording(monitor=True, monitor_source=monitor_source)
            time.sleep(1.0)
            recorder.stop_recording(label='selftest_system')
            results['system']['ok'] = True
            results['system']['message'] = f'System audio recording succeeded (source: {monitor_source})'
            logger.info('System audio self-test succeeded')
    except FileNotFoundError:
        results['system']['message'] = 'parec/pulseaudio not installed'
        logger.warning(results['system']['message'])
    except Exception as e:
        results['system']['message'] = f'System audio test failed: {e}'
        logger.warning(results['system']['message'])

    return results


def main():
    ensure_pulseaudio()
    # Run a short audio self-test and log results before launching UI
    try:
        test_results = run_audio_self_test()
        logger.info(f'Audio self-test results: {test_results}')
    except Exception as e:
        logger.warning(f'Audio self-test encountered an error: {e}')
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == '__main__':
    main()
