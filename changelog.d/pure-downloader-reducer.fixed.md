The downloader example reducer now derives elapsed time from tick actions instead of reading the wall clock, keeping the reducer deterministic and replayable.
