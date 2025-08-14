import os
import time

def fix_database_lock():
    """Fix the database lock issue by removing the journal file"""
    print("Attempting to fix database lock issue...")
    
    # Path to the session files
    session_file = "media_handler_session.session"
    journal_file = "media_handler_session.session-journal"
    
    # Check if the journal file exists
    if os.path.exists(journal_file):
        print(f"Found journal file: {journal_file}")
        try:
            # Try to remove the journal file
            os.remove(journal_file)
            print(f"Successfully removed {journal_file}")
        except Exception as e:
            print(f"Error removing journal file: {str(e)}")
    else:
        print(f"Journal file {journal_file} not found")
    
    # Wait a moment
    time.sleep(1)
    
    # Check if the main session file exists
    if os.path.exists(session_file):
        print(f"Found session file: {session_file}")
        try:
            # Try to remove the main session file
            os.remove(session_file)
            print(f"Successfully removed {session_file}")
        except Exception as e:
            print(f"Error removing session file: {str(e)}")
    else:
        print(f"Session file {session_file} not found")
    
    print("Database lock fix attempt completed. Try running the bot again.")

if __name__ == "__main__":
    fix_database_lock()