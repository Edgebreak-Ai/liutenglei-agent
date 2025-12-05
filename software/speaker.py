from __future__ import annotations
import sys
import time
import threading
import os
from typing import Optional

# Initialize as None - will be imported lazily
np = None
sd = None
PiperVoice = None

def find_model_file(filename: str) -> str:
    """Search for model file in multiple locations."""
    # Check current directory
    if os.path.exists(filename):
        return filename
    
    # Check in common model directories
    model_dirs = [
        "models",
        "voice_models",
        os.path.expanduser("~/.piper/models"),
        os.path.join(os.path.dirname(__file__), "models")
    ]
    
    for model_dir in model_dirs:
        model_path = os.path.join(model_dir, filename)
        if os.path.exists(model_path):
            return model_path
    
    # Check if file exists with different extensions
    possible_names = [filename]
    if not filename.endswith('.onnx'):
        possible_names.append(filename + '.onnx')
    
    for name in possible_names:
        if os.path.exists(name):
            return name
        for model_dir in model_dirs:
            model_path = os.path.join(model_dir, name)
            if os.path.exists(model_path):
                return model_path
    
    return filename  # Return original if not found

def speak(text: str, stop_event: Optional[threading.Event] = None) -> None:
    global np, sd, PiperVoice

    # Lazy import dependencies
    if np is None or sd is None or PiperVoice is None:
        try:
            import numpy as _np
            import sounddevice as _sd
            from piper.voice import PiperVoice as _PiperVoice
            np, sd, PiperVoice = _np, _sd, _PiperVoice
        except Exception as e:
            print(f"❌ Speaker: Missing dependency or import error: {e}", file=sys.stderr)
            return

    model_file = "en_GB-northern_english_male-medium.onnx"
    actual_model_path = find_model_file(model_file)
    
    if not os.path.exists(actual_model_path):
        print(f"❌ Speaker: Model file not found: {actual_model_path}")
        print("   Searched in:", os.getcwd())
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.endswith('.onnx'):
                    print(f"   Found ONNX file: {os.path.join(root, file)}")
        return

    
    try:
        voice = PiperVoice.load(actual_model_path)
    except Exception as e:
        print(f"❌ Speaker: Failed to load voice model: {e}", file=sys.stderr)
        return

    # Limit text length to prevent issues
    if len(text) > 500:
        text = text[:500] + "..."

    try:
        audio_chunks = []
        sample_rate = None
        
        # Synthesize the text and get audio chunks
        synthesis_result = voice.synthesize(text)
        
        # Check the type of synthesis result - it might be different in newer versions
        if hasattr(synthesis_result, 'audio_bytes') and hasattr(synthesis_result, 'sample_rate'):
            # Newer Piper version: single result object
            sample_rate = synthesis_result.sample_rate
            audio_data = np.frombuffer(synthesis_result.audio_bytes, dtype=np.int16)
            audio_chunks.append(audio_data)
        elif hasattr(synthesis_result, '__iter__'):
            # Older version: iterable of audio chunks
            for audio_chunk in synthesis_result:
                if stop_event and stop_event.is_set():
                    return
                
                if sample_rate is None:
                    sample_rate = getattr(audio_chunk, 'sample_rate', 22050)
                
                try:
                    # Try different attribute names for audio data
                    if hasattr(audio_chunk, 'audio_bytes'):
                        audio_data = np.frombuffer(audio_chunk.audio_bytes, dtype=np.int16)
                    elif hasattr(audio_chunk, 'audio'):
                        audio_data = np.frombuffer(audio_chunk.audio, dtype=np.int16)
                    elif hasattr(audio_chunk, 'audio_int16_bytes'):
                        audio_data = np.frombuffer(audio_chunk.audio_int16_bytes, dtype=np.int16)
                    else:
                        # Try to access the object as if it's the audio data itself
                        try:
                            audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
                        except:
                            print(f"⚠️ Unknown audio chunk format: {type(audio_chunk)}")
                            continue
                    
                    audio_chunks.append(audio_data)
                except Exception as e:
                    print(f"⚠️ Speaker: Error processing audio chunk: {e}")
                    print(f"   Chunk type: {type(audio_chunk)}")
                    print(f"   Chunk attributes: {dir(audio_chunk)}")
                    continue
        else:
            print(f"❌ Unknown synthesis result type: {type(synthesis_result)}")
            return

        if not audio_chunks:
            print("❌ Speaker: No audio chunks generated")
            return

        # Combine all audio chunks
        combined_audio = np.concatenate(audio_chunks)
        
        if sample_rate is None:
            sample_rate = 22050  # Default sample rate

        
        sd.play(combined_audio, samplerate=sample_rate, blocking=False)
        
        # Wait for playback to complete or stop event
        start_time = time.time()
        while time.time() - start_time < 30:  # 30 second timeout
            if stop_event and stop_event.is_set():
                sd.stop()
                
                return
            
            try:
                current_stream = sd.get_stream()
                if not current_stream or not current_stream.active:
                    break
            except:
                break
            
            time.sleep(0.1)

    except Exception as e:
        print(f"❌ Speaker: Error during synthesis/playback: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
# Test function
def test_speaker():
    """Test the speaker functionality"""
    print("🧪 Testing speaker...")
    speak("Hello, this is a test message from your AI assistant.")

if __name__ == "__main__":
    test_speaker()