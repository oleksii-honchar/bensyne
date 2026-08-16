# File Watcher Debounce Behavior

The file watcher uses chokidar to monitor the watch directory for changes.
To avoid processing rapid consecutive file changes, a debounce of 5000 ms
is configured in the watch source settings.

When a file is modified, chokidar emits a change event. The debounce timer
resets on each new event, ensuring only the final state after a burst of
changes is processed. The debounce value of 5000 milliseconds provides
enough time for editors to finish writing and for the filesystem to settle.

The file watcher service reads debounceMs from the watch source config,
defaulting to 5000 if not specified.
