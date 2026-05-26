#!/usr/bin/env python3
"""Process and print transcripts for session 12 using actual logic.

This script will:
- Connect to the project's SQLite database (chronicle.db)
- Scan the session audio folder for session 12 (sessions/session_012/audio/)
- For each audio chunk, check if a transcript with the same source and timestamp
  already exists in the database. If not, transcribe the chunk using
  TranscriptionProcessor and store the result in the DB.
- Finally, print all transcripts for session 12.

Run:
    python test_process_session12.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from storage.database import Database
from transcription.processor import TranscriptionProcessor


def session_path_for(session_id: int) -> Path:
    return Path('sessions') / f'session_{session_id:03d}'


def main():
    session_id = 12
    db = Database('chronicle.db')
    db.connect()

    session_path = session_path_for(session_id)
    audio_base = session_path / 'audio'

    processor = TranscriptionProcessor(str(session_path), db=db)

    # Load existing transcripts to avoid duplicates (compare by source and timestamp)
    existing = set()
    try:
        transcripts = db.get_transcripts(session_id)
        for t in transcripts:
            # DB stores timestamp as integer seconds
            existing.add((t['source'], int(t['timestamp'])))
    except Exception:
        transcripts = []

    print(f"Session path: {session_path}")
    print(f"Audio base: {audio_base}")

    # Ensure model is loaded (Parakeet/Coqui or mock)
    try:
        processor.load_model()
    except Exception as e:
        print(f"Warning: failed to load model: {e} (will attempt mock transcription)")

    # Gather audio files from mic and system directories
    new_added = 0
    for source_dir, source_label in (('mic', 'microphone'), ('system', 'system')):
        dir_path = audio_base / source_dir
        if not dir_path.exists():
            print(f"No directory: {dir_path} (skipping {source_label})")
            continue

        wav_files = sorted(dir_path.glob('*.wav'), key=lambda p: p.stat().st_mtime)
        print(f"Found {len(wav_files)} files in {dir_path} for source {source_label}")

        for wf in wav_files:
            try:
                ts = processor._extract_timestamp(wf)
                ts_int = int(ts.timestamp())
            except Exception:
                ts = datetime.fromtimestamp(wf.stat().st_mtime)
                ts_int = int(ts.timestamp())

            if (source_label, ts_int) in existing:
                print(f"Skipping already-transcribed: {wf.name} ({source_label} @ {ts})")
                continue

            print(f"Transcribing (using processor logic): {wf.name} ({source_label} @ {ts})")
            try:
                result = processor._transcribe_and_store(wf, session_id, source_label)
                if result:
                    existing.add((source_label, ts_int))
                    new_added += 1
                    # result['text'] may be datetime object in timestamp; ensure str
                    print(f"  Stored transcript (preview): {result.get('text','')[:120]}")
                else:
                    print(f"  Transcription failed for {wf.name}")
            except Exception as e:
                print(f"  Error transcribing/storing {wf.name}: {e}")

    if new_added == 0:
        print("No new transcripts were added.")
    else:
        print(f"Added {new_added} new transcripts.")

    # Fetch and print all transcripts for the session
    print('\n' + '=' * 60)
    print(f"Transcripts for session {session_id}:")
    print('=' * 60)
    all_ts = db.get_transcripts(session_id)
    if not all_ts:
        print('(no transcripts)')
    else:
        for t in all_ts:
            ts_human = datetime.fromtimestamp(t['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{ts_human}] [{t['source']}]\n  {t['text']}")

    db.disconnect()


if __name__ == '__main__':
    main()
