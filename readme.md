# Software for Pico TR-Cowbell Midi Rhythm Composer Bell

- `boot_pico.py` boot file for the pico to make the storage writable by default. Set to non-writeable if user holds up button during bootup.
- `code_pico.py` code file for the pico w connected to the sequencer. Saving loops requires using the `boot.py` file also for a writable drive.
- `code_display.py` code file for the Feather TFT (or other device) connected via UART to the sequencer pico.
- `saved_loops.py` old way to save loops for loading into the sequencer. Unusd by current version, kept for posterity.
- `saved_loops.json` current way to save loops for loading into the sequencer. The app can append new loops into this file if the drive is writable. User can cycle through and load loops saved into here. 


Thank you to DJDevon3 for publishing this Open Hardware device!