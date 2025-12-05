import os
import pyperclip  # You'll need to install this: pip install pyperclip

def read_files_and_copy_to_clipboard():
    # Get the current script's filename
    current_script = os.path.basename(__file__)
    
    # Get all files in current directory
    files = os.listdir('.')
    
    # Filter out directories and the current script
    files = [f for f in files if os.path.isfile(f) and f != current_script]
    
    # Sort for consistent output
    files.sort()
    
    # Read each file and create the output string
    file_contents = []
    
    for filename in files:
        try:
            # Try to read as text file
            with open(filename, 'r', encoding='utf-8') as file:
                content = file.read()
                # Escape special characters for safe printing
                content = content.replace('\n', '\\n').replace('\r', '\\r').replace(',', '\\,')
                file_contents.append(f"{filename}:{content}")
        except (UnicodeDecodeError, PermissionError):
            # Skip binary files or files we can't read
            file_contents.append(f"{filename}:[BINARY_FILE]")
    
    # Create the final string
    result = ','.join(file_contents)
    
    # Copy to clipboard
    try:
        pyperclip.copy(result)
        print("File contents copied to clipboard successfully!")
        print(f"Processed {len(files)} files.")
    except Exception as e:
        print(f"Failed to copy to clipboard: {e}")
        print("Output:")
        print(result)

if __name__ == "__main__":
    read_files_and_copy_to_clipboard()
