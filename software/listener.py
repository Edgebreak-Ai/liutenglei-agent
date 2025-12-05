"""Wake-word listener using VOSK and sounddevice.

Provides `listen_for_wake_and_task` which waits for a wake word (default "jarvis"),
then transcribes until silence and returns the transcribed message.

Requires: pip install vosk sounddevice
Download a vosk model (small English is fine) and pass its path via `model_path` or
place it in the current working directory under the folder name `model`.
"""
from typing import Optional, List
import os
import time


def listen_for_wake_and_task(wake_word: str = "jarvis",
                             model_path: Optional[str] = "software\\vosk-model-small-en-us-0.15",
                             sample_rate: int = 16000,
                             timeout: float = 60.0,
                             silence_timeout: float = 1.0) -> str:
    """Listen for a wake word, then transcribe speech until silence.

    Returns the transcribed text (empty string on timeout, or an error message
    starting with 'error:' when a dependency/model is missing).
    """
    try:
        import queue
        import json
        import vosk
        import sounddevice as sd
    except Exception as e:
        return f"error: missing dependency ({e})"

    # try to auto-find a model folder if model_path not provided
    if not model_path:
        candidates = ["model", "vosk-model-small-en-us-0.15"]
        for c in candidates:
            if os.path.isdir(c):
                model_path = c
                break

    if not model_path or not os.path.exists(model_path):
        return "error: VOSK model not found. Set model_path or place a model folder named 'model' in the cwd."

    try:
        model = vosk.Model(model_path)
    except Exception as e:
        return f"error: failed to load VOSK model ({e})"

    rec = vosk.KaldiRecognizer(model, sample_rate)
    q: "queue.Queue[bytes]" = queue.Queue()

    def _callback(indata, frames, time_info, status):
        # indata is bytes-like for RawInputStream with dtype='int16'
        if status:
            # non-fatal status; keep running
            try:
                print(f"audio status: {status}")
            except Exception:
                pass
        q.put(bytes(indata))

    collected: List[str] = []
    awakened = False
    last_activity = None
    start = time.time()

    try:
        with sd.RawInputStream(samplerate=sample_rate, blocksize=8000, dtype='int16', channels=1, callback=_callback):
            while True:


                try:
                    chunk = q.get(timeout=0.25)
                except queue.Empty:
                    # check for silence when awakened
                    if awakened and last_activity and (time.time() - last_activity) > float(silence_timeout):
                        break
                    continue

                if rec.AcceptWaveform(chunk):
                    try:
                        res = json.loads(rec.Result())
                    except Exception:
                        res = {}
                    text = res.get('text', '').strip()
                    if not awakened:
                        if text and wake_word.lower() in text.lower().split():
                            awakened = True
                            # remove wake word from first capture
                            words = [w for w in text.split() if w.lower() != wake_word.lower()]
                            if words:
                                collected.append(' '.join(words))
                            last_activity = time.time()
                        else:
                            # keep listening for wake
                            continue
                    else:
                        if text:
                            collected.append(text)
                            last_activity = time.time()
                else:
                    # partial result indicates activity
                    try:
                        partial = json.loads(rec.PartialResult()).get('partial', '').strip()
                    except Exception:
                        partial = ''
                    if awakened and partial:
                        last_activity = time.time()

    except Exception as e:
        return f"error: exception while listening ({e})"

    result = ' '.join(collected).strip()
    return result


if __name__ == '__main__':
    # Simple CLI tester
    print("Listening for wake word 'Jarvis' - speak after the wake word. Ctrl+C to stop.")
    out = listen_for_wake_and_task()
    print(f"Captured: {out}")
