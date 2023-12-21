import os, json, time, random, sys, datetime, ast
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired
import sqlite3


load_dotenv("doc.env")
username = os.environ.get("IG_USERNAME")
email = os.environ.get("IG_EMAIL")
password = os.environ.get("IG_PASSWORD")
target_username = os.environ.get("TARGET_USERNAME")

login_only = ast.literal_eval(os.environ.get("LOGIN_ONLY"))

def init_db():
    conn = sqlite3.connect('clips.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY,
            clip_pk TEXT,
            file_path TEXT,
            file_order INTEGER,
            caption TEXT,
            publisher TEXT,
            tagged_users TEXT,
            reel_url TEXT  
        )
    ''')
    conn.commit()
    conn.close()






def insert_clip_data(clip_pk, file_path, caption, publisher, tagged_users, reel_url):
    conn = sqlite3.connect('clips.db')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clips (clip_pk, file_path, file_order, caption, publisher, tagged_users, reel_url)
        VALUES (?, ?, (SELECT IFNULL(MAX(file_order), 0) + 1 FROM clips), ?, ?, ?, ?)
    """, (clip_pk, file_path, caption, publisher, tagged_users, reel_url))
    conn.commit()
    conn.close()





def authenticate(client, session_file):
    if os.path.exists(session_file):
        client.load_settings(session_file)
        try:
            client.login(username, password)
            client.get_timeline_feed()  # check if the session is valid
        except LoginRequired:
            # session is invalid, re-login and save the new session
            client.login(username, password)
            client.dump_settings(session_file)
    else:
        client.login(username, password)
        client.dump_settings(session_file)


def load_seen_messages(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return set(json.load(f))
    else:
        return set()


def save_seen_messages(file, messages):
    with open(file, "w") as f:
        json.dump(list(messages), f)


def get_now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sleep_countdown():
    # check for new messages every random seconds
    sleep_time = random.randint(30 * 60, 60 * 60)
    print(f"[{get_now()}] Timeout duration: {sleep_time} seconds.")

    for remaining_time in range(sleep_time, 0, -1):
        sys.stdout.write(f"\r[{get_now()}] Time remaining: {remaining_time} second(s).")
        sys.stdout.flush()
        time.sleep(1)

    sys.stdout.write("\n")

def download_clip(client, clip_pk):
    print(f"[{get_now()}] Downloading reel {clip_pk}")

    # Get the current working directory
    cwd = os.getcwd()

    # Construct the path to the download folder
    download_path = os.path.join(cwd, "download")

    # Check if the download folder exists
    if not os.path.exists(download_path):
        os.makedirs(download_path)
        print(f"[{get_now()}] Created {download_path}")

    filename = client.video_download(clip_pk, download_path)
    full_path = str(filename)  # Convert WindowsPath to string
    relative_path = os.path.relpath(full_path, start=os.path.join(os.getcwd(), "bot"))
    formatted_path = relative_path.replace('\\', '\\\\').lstrip('.\\')
    print(f"[{get_now()}] Downloaded to {relative_path}")
    client.delay_range = [1, 3]

    media_info = client.media_info(clip_pk)
    caption = media_info.caption_text if media_info.caption_text else ""
    publisher = media_info.user.username if media_info.user else ""
    tagged_users = ','.join([tag.user.username for tag in media_info.usertags]) if media_info.usertags else ""
    try:
        shortcode = media_info.code
        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
    except AttributeError:
        reel_url = "URL not available"  # Or handle as you see fit

    return formatted_path, caption, publisher, tagged_users, reel_url

def main():
    cl = Client()
    cl.delay_range = [1, 3]

    # Initialize the database
    init_db()

    cl = Client()

    session_file = "session.json"
    seen_messages_file = "seen_messages.json"
    authenticate(cl, session_file)

    user_id = cl.user_id_from_username(username)
    print(f"[{get_now()}] Logged in as user ID {user_id}")

    if login_only:
        print(f"[{get_now()}] LOGIN_ONLY is set to true, the script ends here")
        return

    seen_message_ids = load_seen_messages(seen_messages_file)
    print(f"[{get_now()}] Loaded seen messages.")

    while True:
        try:
            threads = cl.direct_threads()
            print(f"[{get_now()}] Retrieved direct threads.")
            cl.delay_range = [1, 3]

            for thread in threads:
                thread_id = thread.id
                messages = cl.direct_messages(thread_id)
                print(f"[{get_now()}] Retrieved messages.")
                cl.delay_range = [1, 3]

                for message in messages:
                    sender_username = cl.user_info(message.user_id).username
                    if sender_username == target_username:
                        if message.id not in seen_message_ids and message.item_type == "clip" and message.clip:
                            file_path, caption, publisher, tagged_users, reel_url = download_clip(cl, message.clip.pk)
                            if file_path:
                                insert_clip_data(message.clip.pk, file_path, caption, publisher, tagged_users, reel_url)
                                seen_message_ids.add(message.id)
                                save_seen_messages(seen_messages_file, seen_message_ids)
                        match message.item_type:
                            case "clip":
                                print(
                                    f"[{get_now()}] Downloading reel {message.clip.pk}"
                                )
                                try:
                                    download_clip(cl, message.clip.pk)
                                except Exception as e:
                                    print(e)
                            case "xma_story_share":
                                print(
                                    f"[{get_now()}] New story video in thread {thread_id}: {message.id}"
                                )
                            case _:
                                print(
                                    f"[{get_now()}] New message in thread {thread_id}: {message.text}"
                                )
                        seen_message_ids.add(message.id)
                        save_seen_messages(seen_messages_file, seen_message_ids)

        except Exception as e:
            print(f"[{get_now()}] An exception occurred: {e}")
            print(f"[{get_now()}] Deleting the session file and restarting the script.")
            if os.path.exists(session_file):
                os.remove(session_file)
            sleep_countdown()
            print(f"[{get_now()}] Restarting the script now.")
            os.execv(sys.executable, ["python"] + sys.argv)

        sleep_countdown()

if __name__ == "__main__":
    main()