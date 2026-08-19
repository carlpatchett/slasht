from time import sleep


class RecoverableFault(Exception):
    """A hiccup that clears up on its own."""


def run_with_backoff(task, tries=6, initial_pause=0.25):
    """Run task, retrying recoverable hiccups with pauses."""
    for round_index in range(tries):
        try:
            return task()
        except RecoverableFault:
            if round_index == tries - 1:
                raise
            pause = initial_pause * (2 ** round_index)
            sleep(pause)
    return None
