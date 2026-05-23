# Build Plan

| BU    | Name               | Status  | Depends On      | Next  |
|-------|--------------------|---------|-----------------|-------|
| BU001 | App Bootstrap      | Pending | none            | BU002 |
| BU002 | SQLite Storage     | Pending | BU001           | BU003 |
| BU003 | Audio Recording    | Pending | BU002           | BU004 |
| BU004 | Screenshot Capture | Pending | BU002           | BU005 |
| BU005 | Parakeet Transcription | Pending | BU003           | BU006 |
| BU006 | Session Management | Pending | BU004, BU005    | BU007 |
| BU007 | Summary Generation | Pending | BU006           | BU008 |
| BU008 | UI Integration     | Pending | BU006, BU007    | BU009 |
| BU009 | Notion Sync        | Pending | BU008           | none  |
