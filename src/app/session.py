"""Session class for meeting lifecycle management."""
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Session:
    """Represents a single meeting capture session.
    
    Manages the lifecycle of a recording session including audio recording,
    screenshots, and transcription. Coordinates all components and maintains
    session state.
    """
    
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_STOPPED = 'stopped'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    
    def __init__(self, 
                 session_id: int,
                 name: str,
                 session_path: str,
                 db=None):
        """Initialize a Session instance.
        
        Args:
            session_id: Database session ID
            name: Session name/title
            session_path: Path to session directory
            db: Database instance for persistence
        """
        self.id = session_id
        self.name = name
        self.session_path = Path(session_path)
        self.db = db
        
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.status = self.STATUS_STOPPED
        
        # Component references (set by SessionManager)
        self.audio_recorder = None
        self.screenshot_capture = None
        self.transcription_processor = None
        
        # Session data
        self.audio_files: List[str] = []
        self.screenshot_files: List[str] = []
        
        # Ensure session directory exists
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create session directory structure if it doesn't exist."""
        self.session_path.mkdir(parents=True, exist_ok=True)
        (self.session_path / 'audio').mkdir(parents=True, exist_ok=True)
        (self.session_path / 'screenshots').mkdir(parents=True, exist_ok=True)
        (self.session_path / 'transcripts').mkdir(parents=True, exist_ok=True)
    
    def start(self) -> None:
        """Start the session and initialize all components."""
        if self.status == self.STATUS_ACTIVE:
            logger.warning(f'Session {self.id} is already active')
            return
        
        self.start_time = datetime.now()
        self.status = self.STATUS_ACTIVE
        
        # Update database
        if self.db:
            self.db.update_session(self.id, status=self.STATUS_ACTIVE)
        
        # Initialize audio recorder
        if self.audio_recorder:
            self.audio_recorder.session_path = str(self.session_path)
            self.audio_recorder.start_time = self.start_time
        
        # Initialize screenshot capture
        if self.screenshot_capture:
            self.screenshot_capture.session_path = str(self.session_path)
            self.screenshot_capture.start_time = self.start_time
        
        logger.info(f'Session {self.id} started: {self.name}')
    
    def pause(self) -> None:
        """Pause the session (pause audio recording)."""
        if self.status != self.STATUS_ACTIVE:
            logger.warning(f'Session {self.id} is not active, cannot pause')
            return
        
        self.status = self.STATUS_PAUSED
        if self.db:
            self.db.update_session(self.id, status=self.STATUS_PAUSED)
        
        logger.info(f'Session {self.id} paused')
    
    def resume(self) -> None:
        """Resume the session from paused state."""
        if self.status != self.STATUS_PAUSED:
            logger.warning(f'Session {self.id} is not paused, cannot resume')
            return
        
        self.status = self.STATUS_ACTIVE
        if self.db:
            self.db.update_session(self.id, status=self.STATUS_ACTIVE)
        
        logger.info(f'Session {self.id} resumed')
    
    def stop(self) -> None:
        """Stop the session and all components."""
        if self.status not in (self.STATUS_ACTIVE, self.STATUS_PAUSED):
            logger.warning(f'Session {self.id} is not running')
            return
        
        self.end_time = datetime.now()
        self.status = self.STATUS_STOPPED
        
        # Update database
        if self.db:
            self.db.update_session(
                self.id, 
                status=self.STATUS_STOPPED,
                end_time=int(self.end_time.timestamp())
            )
        
        logger.info(f'Session {self.id} stopped: {self.name}')
    
    def start_recording(self, label: str = 'recording', monitor: bool = False) -> str:
        """Start audio recording.
        
        Args:
            label: Label for the recording
            monitor: Whether to record system audio
            
        Returns:
            Path to the recording file
        """
        if not self.audio_recorder:
            raise RuntimeError('Audio recorder not configured')
        
        if not self.start_time:
            self.start()
        
        if monitor:
            self.audio_recorder.start_recording(monitor=True)
        else:
            self.audio_recorder.start_recording()
        
        return str(self.session_path / 'audio')
    
    def stop_recording(self, label: str = 'recording') -> Optional[str]:
        """Stop audio recording.
        
        Args:
            label: Label for the recording
            
        Returns:
            Path to the saved audio file, or None if not recording
        """
        if not self.audio_recorder:
            return None
        
        output_path = self.audio_recorder.stop_recording(label)
        
        if output_path:
            self.audio_files.append(output_path)
        
        return output_path
    
    def capture_screenshot(self, label: str = 'screenshot') -> str:
        """Capture a screenshot.
        
        Args:
            label: Label for the screenshot
            
        Returns:
            Path to the saved screenshot
        """
        if not self.screenshot_capture:
            raise RuntimeError('Screenshot capture not configured')
        
        if not self.start_time:
            self.start()
        
        output_path = self.screenshot_capture.capture_fullscreen(
            label=label, 
            session_id=self.id
        )
        
        self.screenshot_files.append(output_path)
        return output_path
    
    def process_transcriptions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Process all audio files for transcription.
        
        Returns:
            Dictionary with transcription results by source
        """
        if not self.transcription_processor:
            logger.warning('Transcription processor not configured')
            return {'microphone': [], 'system': []}
        
        self.status = self.STATUS_PROCESSING
        if self.db:
            self.db.update_session(self.id, status=self.STATUS_PROCESSING)
        
        try:
            results = self.transcription_processor.process_all(self.id)
            self.status = self.STATUS_COMPLETED
            if self.db:
                self.db.update_session(self.id, status=self.STATUS_COMPLETED)
            return results
        except Exception as e:
            logger.error(f'Transcription processing failed: {str(e)}')
            self.status = self.STATUS_STOPPED
            if self.db:
                self.db.update_session(self.id, status=self.STATUS_STOPPED)
            raise
    
    def get_duration(self) -> Optional[float]:
        """Get session duration in seconds.
        
        Returns:
            Duration in seconds, or None if session hasn't ended
        """
        if not self.start_time:
            return None
        
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get session summary information.
        
        Returns:
            Dictionary with session metadata
        """
        return {
            'id': self.id,
            'name': self.name,
            'session_path': str(self.session_path),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.get_duration(),
            'status': self.status,
            'audio_count': len(self.audio_files),
            'screenshot_count': len(self.screenshot_files)
        }
    
    def __repr__(self) -> str:
        return f'Session(id={self.id}, name={self.name!r}, status={self.status!r})'
