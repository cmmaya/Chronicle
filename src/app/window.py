from PySide6.QtWidgets import (QMainWindow, QMenuBar, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QStatusBar,
                               QMessageBox, QCheckBox, QComboBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction

from .session_manager import SessionManager


class MainWindow(QMainWindow):
    """Main application window with session controls."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Chronicle')
        self.resize(800, 600)
        
        # Get project root directory (parent of src/)
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sessions_path = os.path.join(project_root, 'sessions')
        
        # Session manager
        self.session_manager: SessionManager = None
        
        # UI state
        self._is_recording = False
        
        # Create UI components
        self._create_menu_bar()
        self._create_central_widget()
        self._create_status_bar()
        # Timer to poll recorder status while recording
        self._status_timer = QTimer()
        self._status_timer.setInterval(500)  # ms
        self._status_timer.timeout.connect(self._poll_capture_status)
        
        # Initialize session manager
        self._init_session_manager(sessions_path)
        
    def _init_session_manager(self, sessions_path: str):
        """Initialize the session manager.
        
        Args:
            sessions_path: Path to sessions directory
        """
        try:
            self.session_manager = SessionManager(
                base_path=sessions_path,
                db_path='chronicle.db'
            )
            self._update_ui_state()
            self.status_label.setText('Ready')
        except Exception as e:
            self.status_label.setText(f'Error: {str(e)}')
            QMessageBox.critical(self, 'Error', f'Failed to initialize: {str(e)}')

    def _load_settings(self):
        if not getattr(self, '_settings', None):
            return
        try:
            mic = self._settings.value('record_microphone', True, type=bool)
            system = self._settings.value('record_system', True, type=bool)
            mic_index = self._settings.value('mic_device_index', -1, type=int)
            system_index = self._settings.value('system_device_index', -1, type=int)
            self.mic_checkbox.setChecked(bool(mic))
            self.system_checkbox.setChecked(bool(system))
            # mic_device_selector will be set after population
            self._saved_mic_index = mic_index
            self._saved_system_index = system_index
        except Exception:
            self._saved_mic_index = -1
            self._saved_system_index = -1

    def _save_settings(self):
        if not getattr(self, '_settings', None):
            return
        try:
            self._settings.setValue('record_microphone', self.mic_checkbox.isChecked())
            self._settings.setValue('record_system', self.system_checkbox.isChecked())
            self._settings.setValue('mic_device_index', self.mic_device_selector.currentData() or -1)
            self._settings.setValue('system_device_index', self.system_device_selector.currentData() or -1)
            self._settings.sync()
        except Exception:
            pass

    def _populate_mic_devices(self):
        # Try to populate input devices via sounddevice
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            self.mic_device_selector.clear()
            added = False
            for idx, dev in enumerate(devices):
                try:
                    if dev.get('max_input_channels', 0) > 0:
                        name = f"{dev.get('name')} (idx={idx})"
                        self.mic_device_selector.addItem(name, idx)
                        added = True
                except Exception:
                    continue
            if added:
                self.mic_device_selector.setEnabled(True)
                # restore saved index if any
                try:
                    if getattr(self, '_saved_mic_index', -1) is not None and int(self._saved_mic_index) >= 0:
                        # find matching index in combobox data
                        for i in range(self.mic_device_selector.count()):
                            if self.mic_device_selector.itemData(i) == int(self._saved_mic_index):
                                self.mic_device_selector.setCurrentIndex(i)
                                break
                except Exception:
                    pass
            else:
                self.mic_device_selector.setEnabled(False)
        except Exception:
            # sounddevice not available or query failed
            self.mic_device_selector.clear()
            self.mic_device_selector.setEnabled(False)

    def _populate_system_devices(self):
        # Populate candidate system capture devices (loopback / stereo mix)
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            self.system_device_selector.clear()
            added = False
            for idx, dev in enumerate(devices):
                try:
                    name = str(dev.get('name', '')).lower()
                    # Candidate: input-capable devices that mention loopback/stereo mix or wave out
                    if dev.get('max_input_channels', 0) > 0 and ('loopback' in name or 'stereo mix' in name or 'wave out' in name or 'loop back' in name):
                        disp = f"{dev.get('name')} (idx={idx})"
                        self.system_device_selector.addItem(disp, idx)
                        added = True
                except Exception:
                    continue
            if added:
                self.system_device_selector.setEnabled(True)
                try:
                    if getattr(self, '_saved_system_index', -1) is not None and int(self._saved_system_index) >= 0:
                        for i in range(self.system_device_selector.count()):
                            if self.system_device_selector.itemData(i) == int(self._saved_system_index):
                                self.system_device_selector.setCurrentIndex(i)
                                break
                except Exception:
                    pass
            else:
                self.system_device_selector.setEnabled(False)
        except Exception:
            self.system_device_selector.clear()
            self.system_device_selector.setEnabled(False)
    
    def _create_menu_bar(self):
        """Create the application menu bar."""
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu('File')
        
        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        session_menu = menu_bar.addMenu('Session')
        
        # Start session action
        start_action = QAction('Start Session', self)
        start_action.triggered.connect(self._on_start_session)
        session_menu.addAction(start_action)
        
        # Stop session action
        stop_action = QAction('Stop Session', self)
        stop_action.triggered.connect(self._on_stop_session)
        session_menu.addAction(stop_action)
        
        help_menu = menu_bar.addMenu('Help')
        
        # About action
        about_action = QAction('About', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
        self.setMenuBar(menu_bar)
    
    def _create_central_widget(self):
        """Create the central widget with session controls."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Title
        title_label = QLabel('Chronicle')
        title_label.setAlignment(Qt.AlignCenter)
        title_font = title_label.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Session name input area
        session_layout = QHBoxLayout()
        session_layout.addStretch()
        self.session_name_label = QLabel('Session Name:')
        self.session_name_label.setFont(title_font)
        self.session_name_input = QLabel('New Session')
        self.session_name_input.setFont(title_font)
        session_layout.addWidget(self.session_name_label)
        session_layout.addWidget(self.session_name_input)
        session_layout.addStretch()
        layout.addLayout(session_layout)

        # Microphone capture checkbox
        mic_layout = QHBoxLayout()
        mic_layout.addStretch()
        self.mic_checkbox = QCheckBox('Record microphone')
        self.mic_checkbox.setChecked(True)
        mic_layout.addWidget(self.mic_checkbox)
        # Microphone device selector
        self.mic_device_selector = QComboBox()
        self.mic_device_selector.setEnabled(False)
        mic_layout.addWidget(self.mic_device_selector)
        # Microphone status indicator
        self.mic_status_label = QLabel('')
        mic_layout.addWidget(self.mic_status_label)
        mic_layout.addStretch()
        layout.addLayout(mic_layout)

        # System audio capture checkbox
        system_layout = QHBoxLayout()
        system_layout.addStretch()
        self.system_checkbox = QCheckBox('Record system audio')
        self.system_checkbox.setChecked(True)
        system_layout.addWidget(self.system_checkbox)
        # System device selector
        self.system_device_selector = QComboBox()
        self.system_device_selector.setEnabled(False)
        system_layout.addWidget(self.system_device_selector)
        # System status indicator
        self.system_status_label = QLabel('')
        system_layout.addWidget(self.system_status_label)
        system_layout.addStretch()
        layout.addLayout(system_layout)

        # Load persisted settings
        try:
            from PySide6.QtCore import QSettings
            self._settings = QSettings('Chronicle', 'ChronicleApp')
        except Exception:
            self._settings = None

        self._load_settings()
        # Populate devices asynchronously (best-effort)
        self._populate_mic_devices()
        self._populate_system_devices()

        # Save settings on change
        try:
            self.mic_checkbox.stateChanged.connect(self._save_settings)
            self.system_checkbox.stateChanged.connect(self._save_settings)
            self.mic_device_selector.currentIndexChanged.connect(self._save_settings)
            self.system_device_selector.currentIndexChanged.connect(self._save_settings)
        except Exception:
            pass
        
        # Spacer
        layout.addStretch()
        
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.start_button = QPushButton('Start Session')
        self.start_button.setMinimumSize(150, 50)
        self.start_button.setFont(title_font)
        self.start_button.clicked.connect(self._on_start_session)
        
        self.stop_button = QPushButton('Stop Session')
        self.stop_button.setMinimumSize(150, 50)
        self.stop_button.setFont(title_font)
        self.stop_button.clicked.connect(self._on_stop_session)
        self.stop_button.setEnabled(False)
        
        button_layout.addStretch()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Spacer
        layout.addStretch()
        
        # Status display
        self.status_label = QLabel('Ready')
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = self.status_label.font()
        status_font.setPointSize(16)
        self.status_label.setFont(status_font)
        layout.addWidget(self.status_label)
        
        # Spacer at bottom
        layout.addStretch()
    
    def _create_status_bar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Ready')

    def _update_capture_status(self, mic_ok: bool, sys_ok: bool):
        """Update visual indicators for mic/system capture status.

        mic_ok/sys_ok: booleans indicating whether recording streams/processes are active
        """
        try:
            if mic_ok:
                self.mic_status_label.setText('●')
                self.mic_status_label.setStyleSheet('color: green;')
            else:
                self.mic_status_label.setText('○')
                self.mic_status_label.setStyleSheet('color: red;')

            if sys_ok:
                self.system_status_label.setText('●')
                self.system_status_label.setStyleSheet('color: green;')
            else:
                self.system_status_label.setText('○')
                self.system_status_label.setStyleSheet('color: red;')
        except Exception:
            pass

    def _poll_capture_status(self):
        """Poll the current recorder and refresh capture indicators."""
        try:
            recorder = None
            if self.session_manager and self.session_manager.current_session:
                recorder = self.session_manager.current_session.audio_recorder
            mic_ok = False
            sys_ok = False
            if recorder:
                mic_ok = getattr(recorder, 'stream', None) is not None
                sys_ok = (getattr(recorder, 'process', None) is not None) or (getattr(recorder, 'system_stream', None) is not None)
            self._update_capture_status(mic_ok, sys_ok)
        except Exception:
            pass
    
    def _update_ui_state(self):
        """Update UI based on current session state."""
        if self.session_manager is None:
            return
            
        active_session = self.session_manager.get_active_session()
        
        if active_session and active_session.status == 'active':
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self._is_recording = True
            self.status_label.setText('Recording')
            self.session_name_input.setText(active_session.name)
        elif active_session and active_session.status == 'processing':
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status_label.setText('Transcribing...')
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self._is_recording = False
            if active_session and active_session.status == 'completed':
                self.status_label.setText('Completed')
            else:
                self.status_label.setText('Ready')
    
    def _on_start_session(self):
        """Handle start session button click."""
        try:
            # Generate session name with timestamp
            from datetime import datetime
            now = datetime.now()
            session_name = f"Session {now.strftime('%Y-%m-%d %H:%M')}"
            
            # Start session via manager (auto-starts recording)
            mic = bool(self.mic_checkbox.isChecked()) if self.mic_checkbox is not None else True
            system = bool(self.system_checkbox.isChecked()) if self.system_checkbox is not None else True

            mic_device = None
            try:
                mic_device = self.mic_device_selector.currentData()
            except Exception:
                mic_device = None

            system_device = None
            try:
                system_device = self.system_device_selector.currentData()
            except Exception:
                system_device = None

            self.session_manager.start_session(session_name, auto_record=True, mic=mic, mic_device=mic_device, system_device=system_device)

            # Update capture status indicator based on recorder state
            try:
                recorder = None
                if self.session_manager and self.session_manager.current_session:
                    recorder = self.session_manager.current_session.audio_recorder
                mic_ok = False
                sys_ok = False
                if recorder:
                    mic_ok = getattr(recorder, 'stream', None) is not None
                    sys_ok = (getattr(recorder, 'process', None) is not None) or (getattr(recorder, 'system_stream', None) is not None)
                self._update_capture_status(mic_ok, sys_ok)
            except Exception:
                pass
            # start polling status
            try:
                self._status_timer.start()
            except Exception:
                pass
            
            # Update UI
            self._update_ui_state()
            self.status_bar.showMessage(f'Session started: {session_name}')
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to start session: {str(e)}')
            self.status_label.setText(f'Error: {str(e)}')
    
    def _on_stop_session(self):
        """Handle stop session button click."""
        try:
            # Stop recording first
            self.session_manager.stop_recording(label='main')
            # stop polling status
            try:
                self._status_timer.stop()
            except Exception:
                pass
            # reset indicators
            try:
                self._update_capture_status(False, False)
            except Exception:
                pass
            
            # Stop session (this triggers transcription via the manager)
            session = self.session_manager.stop_session()
            
            # Update UI to show processing
            self.status_label.setText('Transcribing...')
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status_bar.showMessage('Processing transcriptions...')
            
            # Process transcriptions in background
            if session:
                # Run transcription in a timer to allow UI to update
                QTimer.singleShot(100, lambda: self._process_transcription(session))
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to stop session: {str(e)}')
            self.status_label.setText(f'Error: {str(e)}')
            self._update_ui_state()
    
    def _process_transcription(self, session):
        """Process transcriptions after session stops."""
        try:
            results = self.session_manager.process_transcriptions()
            
            # Update UI
            self._update_ui_state()
            self.status_bar.showMessage('Transcription completed')
            
            # Show completion message
            mic_count = len(results.get('microphone', []))
            sys_count = len(results.get('system', []))
            QMessageBox.information(
                self, 
                'Session Complete',
                f'Session saved successfully.\n\n'
                f'Microphone transcriptions: {mic_count}\n'
                f'System audio transcriptions: {sys_count}'
            )
            
        except Exception as e:
            QMessageBox.warning(self, 'Warning', f'Transcription failed: {str(e)}')
            self._update_ui_state()
    
    def _show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self,
            'About Chronicle',
            'Chronicle\n\n'
            'Meeting capture and transcription tool.\n\n'
            'Captures audio, screenshots, and generates summaries.'
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Check if there's an active session
        if self.session_manager and self.session_manager.get_active_session():
            reply = QMessageBox.question(
                self,
                'Active Session',
                'There is an active session. Stop and close?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                try:
                    # Stop recording if active
                    self.session_manager.stop_recording(label='main')
                    # Stop session
                    self.session_manager.stop_session()
                except Exception:
                    pass  # Ignore errors during shutdown
                event.accept()
            else:
                event.ignore()
                return
        
        # Clean up session manager
        if self.session_manager:
            try:
                self.session_manager.close()
            except Exception:
                pass
        
        event.accept()
