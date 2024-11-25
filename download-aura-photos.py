import json
import os
import os.path
import re
import shutil
import time
import yaml
import requests
import pathlib

# load config
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

print("config values: ", config)

email = config["accounts"][0]["email"]
password = config["accounts"][0]["password"]
base_file_path = config["base_file_path"]

# Main download function
def download_photos_from_aura(email, password, frame_name, frame_id, image_path):
    # define URLs and payload format
    login_url = "https://api.pushd.com/v5/login.json"
    frame_url = f"https://api.pushd.com/v5/frames/{frame_id}/assets.json?side_load_users=false"
    login_payload = {
        "identifier_for_vendor": "does-not-matter",
        "client_device_id": "does-not-matter",
        "app_identifier": "com.pushd.Framelord",
        "locale": "en",
        "user": {
            "email": email,
            "password": password
        }
    }

    print(f"Logging into frame {frame_name} | {frame_id}")

    # make login request with credentials
    s = requests.Session()
    r = s.post(login_url, json=login_payload)

    if r.status_code != 200:
        print("Login Error: Check your credentials")
        return 0

    print("Login Success")

    # get json and update user and auth token headers for next request
    json_data = r.json()
    s.headers.update({'X-User-Id': json_data['result']['current_user']['id'],
                      'X-Token-Auth': json_data['result']['current_user']['auth_token']})

    # make request to get all phtos (frame assets)
    r = s.get(frame_url)
    json_data = json.loads(r.text)
    counter = 0
    skipped = 0

    # check to make sure the frame assets array exists
    if "assets" not in json_data:
        print("Download Error: No images returned from this Aura Frame. API responded with:")
        print(json_data)
        return 0

    photo_count = len(json_data["assets"])
    print(f"Found {photo_count} photos, starting download process")
    print(f"Downloading pictures to path {image_path} with filename <taken_at>_<file_name>")

    for item in json_data["assets"]:

        try:
            # construct the raw photo URL
            url = f"https://imgproxy.pushd.com/{item['user_id']}/{item['file_name']}"
            # make a unique new_filename using
            #  item['taken_at'] + item['id'] + item['file_name']'s extension
            # But clean the timestamp to be Windows-friendly
            # clean_time = item['taken_at'].replace(':', '-')
            # new_filename = clean_time + "_" + item['id'] + os.path.splitext(item['file_name'])[1]
            new_filename = item['id'] + os.path.splitext(item['file_name'])[1]
            file_to_write = os.path.join(image_path, new_filename)

            # Bump the counter and print the new_filename out to track progress
            counter += 1

            # check if file exists and skip it if so
            if os.path.isfile(file_to_write):
                print(f"{counter}: Skipping {new_filename}, already downloaded")
                skipped += 1
                continue

            # Get the photo from the url
            print(f"{counter}: Downloading {new_filename}")
            response = requests.get(url, stream=True)

            # write to a file
            with open(file_to_write, 'wb') as out_file:
                shutil.copyfileobj(response.raw, out_file)
            del response

            # wait a bit to avoid throttling
            time.sleep(2)

        except KeyboardInterrupt:
            print('Exiting from keyboard interrupt')
            break

        except Exception as e:
            print(f"Errored out on item: {counter}, probably due to throttling")
            print(str(e))
            time.sleep(10)

    return counter - skipped

# Check the output directory exists in case the script is moved
# or the file_path is changed.
# if not os.path.isdir(base_file_path):
#     print(f"Error: output directory {base_file_path} does not exist")
# else:
for frame in config["frames"]:
    image_path = pathlib.Path(base_file_path, frame["frame_id"])
    image_path.mkdir(parents=True, exist_ok=True)
    total = download_photos_from_aura(email, password, frame["name"], frame["frame_id"], image_path)
    print(f"Downloaded {total} photos")