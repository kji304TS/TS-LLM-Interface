import json
import os

def convert_json_to_env():
    """Convert Google service account JSON file to .env format."""
    try:
        # Get the path to the JSON file
        json_path = input("Enter the path to your Google service account JSON file: ").strip()
        
        # Read the JSON file
        with open(json_path, 'r') as f:
            credentials = json.load(f)
        
        # Convert to single line
        credentials_str = json.dumps(credentials)
        
        # Create or update .env file
        env_path = '.env'
        env_content = []
        
        # Read existing .env file if it exists
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_content = f.readlines()
        
        # Update or add GOOGLE_CREDENTIALS_JSON
        credentials_line = f'GOOGLE_CREDENTIALS_JSON={credentials_str}\n'
        found = False
        
        for i, line in enumerate(env_content):
            if line.startswith('GOOGLE_CREDENTIALS_JSON='):
                env_content[i] = credentials_line
                found = True
                break
        
        if not found:
            env_content.append(credentials_line)
        
        # Write back to .env file
        with open(env_path, 'w') as f:
            f.writelines(env_content)
        
        print("\n✅ Successfully updated .env file with Google credentials!")
        print("🔒 Make sure to keep your .env file secure and never commit it to version control.")
        
    except FileNotFoundError:
        print("❌ Error: JSON file not found. Please check the path and try again.")
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON file. Please check the file contents.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("🔄 Google Service Account Credentials Converter")
    print("=" * 50)
    convert_json_to_env() 