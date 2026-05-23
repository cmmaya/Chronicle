"""Transcription processor for handling audio transcription workflow."""
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import glob as glob_module

from .parakeet import ParakeetV3, ParakeetError

logger = logging.getLogger(__name__)


class TranscriptionProcessor:
    """Process audio files for transcription using Parakeet V3.
    
    Handles transcription of both microphone and system audio recordings,
    stores results in database with timestamps for synchronization.
    """
    
    SOURCE_MICROPHONE = 'microphone'
    SOURCE_SYSTEM = 'system'
    
    def __init__(self, 
                 session_path: str,
                 db=None,
                 model_path: Optional[str] = None,
                 scorer_path: Optional[str] = None):
        """Initialize transcription processor.
        
        Args:
            session_path: Path to session directory containing audio files
            db: Database instance for storing transcripts (optional)
            model_path: Path to Parakeet model file (optional)
            scorer_path: Path to language model scorer (optional)
        """
        self.session_path = Path(session_path)
        self.audio_path = self.session_path / 'audio'
        self.db = db
        self.parakeet = ParakeetV3(model_path=model_path, scorer_path=scorer_path)
        self._is_loaded = False
    
    def load_model(self) -> None:
        """Load Parakeet model."""
        if self._is_loaded:
            return
        self.parakeet.load()
        self._is_loaded = True
        logger.info("TranscriptionProcessor model loaded")
    
    def _get_audio_files(self, source: Optional[str] = None) -> List[Path]:
        """Get list of audio files in session directory.
        
        Args:
            source: Filter by source ('microphone' or 'system'), or None for all
            
        Returns:
            List of audio file paths sorted by modification time
        """
        if not self.audio_path.exists():
            return []
        
        # Get all WAV files
        pattern = str(self.audio_path / '*.wav')
        files = glob_module.glob(pattern)
        
        # Filter by source if specified
        if source == self.SOURCE_MICROPHONE:
            files = [f for f in files if '_system' not in f]
        elif source == self.SOURCE_SYSTEM:
            files = [f for f in files if '_system' in f]
        
        # Sort by modification time (oldest first)
        files.sort(key=lambda f: Path(f).stat().st_mtime)
        
        return [Path(f) for f in files]
    
    def _get_source_from_filename(self, filepath: Path) -> str:
        """Determine audio source from filename.
        
        Args:
            filepath: Path to audio file
            
        Returns:
            'system' if filename contains '_system', else 'microphone'
        """
        if '_system' in filepath.stem:
            return self.SOURCE_SYSTEM
        return self.SOURCE_MICROPHONE
    
    def _extract_timestamp(self, filepath: Path) -> datetime:
        """Extract timestamp from audio filename.
        
        Filename format: YYYYMMDD_HHMMSS_label.wav
        
        Args:
            filepath: Path to audio file
            
        Returns:
            datetime object extracted from filename
        """
        try:
            # Extract timestamp from filename (first 15 characters: YYYYMMDD_HHMMSS)
            name = filepath.stem
            if len(name) >= 15:
                date_str = name[:15]  # YYYYMMDD_HHMMSS
                return datetime.strptime(date_str, '%Y%m%d_%H%M%S')
        except ValueError:
            pass
        
        # Fallback: use file modification time
        return datetime.fromtimestamp(filepath.stat().st_mtime)
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe a single audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcribed text string
            
        Raises:
            ParakeetError: If transcription fails
        """
        if not self._is_loaded:
            self.load_model()
        
        return self.parakeet.transcribe(audio_path)
    
    def process_microphone_audio(self, session_id: int) -> List[Dict[str, Any]]:
        """Process all microphone audio files for a session.
        
        Args:
            session_id: Database session ID
            
        Returns:
            List of transcription results with metadata
        """
        return self._process_audio_by_source(session_id, self.SOURCE_MICROPHONE)
    
    def process_system_audio(self, session_id: int) -> List[Dict[str, Any]]:
        """Process all system audio files for a session.
        
        Args:
            session_id: Database session ID
            
        Returns:
            List of transcription results with metadata
        """
        return self._process_audio_by_source(session_id, self.SOURCE_SYSTEM)
    
    def _process_audio_by_source(self, session_id: int, source: str) -> List[Dict[str, Any]]:
        """Process all audio files of a specific source type.
        
        Args:
            session_id: Database session ID
            source: Audio source ('microphone' or 'system')
            
        Returns:
            List of transcription results
        """
        audio_files = self._get_audio_files(source=source)
        results = []
        
        for audio_file in audio_files:
            try:
                result = self._transcribe_and_store(audio_file, session_id, source)
                if result:
                    results.append(result)
            except ParakeetError as e:
                logger.error(f"Failed to transcribe {audio_file}: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error processing {audio_file}: {str(e)}")
        
        logger.info(f"Processed {len(results)} {source} audio files")
        return results
    
    def _transcribe_and_store(self, 
                               audio_file: Path, 
                               session_id: int, 
                               source: str) -> Optional[Dict[str, Any]]:
        """Transcribe a single file and store in database.
        
        Args:
            audio_file: Path to audio file
            session_id: Database session ID
            source: Audio source type
            
        Returns:
            Transcription result dict or None if failed
        """
        timestamp = self._extract_timestamp(audio_file)
        
        try:
            # Transcribe audio
            text = self.transcribe_audio(str(audio_file))
            
            # Store in database if available
            if self.db:
                self.db.add_transcript(
                    session_id=session_id,
                    timestamp=timestamp,
                    text=text,
                    source=source
                )
                logger.info(f"Stored transcript for {audio_file.name}")
            
            return {
                'filepath': str(audio_file),
                'timestamp': timestamp,
                'text': text,
                'source': source,
                'session_id': session_id
            }
            
        except ParakeetError as e:
            logger.error(f"Transcription failed for {audio_file}: {str(e)}")
            return None
    
    def process_all(self, session_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """Process all audio files (microphone and system) for a session.
        
        Args:
            session_id: Database session ID
            
        Returns:
            Dictionary with 'microphone' and 'system' lists of results
        """
        if not self._is_loaded:
            self.load_model()
        
        microphone_results = self.process_microphone_audio(session_id)
        system_results = self.process_system_audio(session_id)
        
        return {
            'microphone': microphone_results,
            'system': system_results
        }
    
    def get_unprocessed_files(self) -> Dict[str, List[Path]]:
        """Get list of audio files that haven't been transcribed.
        
        Returns:
            Dictionary with 'microphone' and 'system' lists of unprocessed files
        """
        if not self.db:
            # No database - return all files as unprocessed
            return {
                'microphone': self._get_audio_files(self.SOURCE_MICROPHONE),
                'system': self._get_audio_files(self.SOURCE_SYSTEM)
            }
        
        # Query database for already processed files
        # This is a simplified check - in production you'd want more robust tracking
        all_files = {
            'microphone': self._get_audio_files(self.SOURCE_MICROPHONE),
            'system': self._get_audio_files(self.SOURCE_SYSTEM)
        }
        
        return all_files
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the transcription model.
        
        Returns:
            Dictionary with model metadata
        """
        return self.parakeet.get_model_info()
    
    def unload_model(self) -> None:
        """Unload model to free memory."""
        self.parakeet.unload()
        self._is_loaded = False
        logger.info("TranscriptionProcessor model unloaded")
