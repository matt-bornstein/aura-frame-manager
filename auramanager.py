import yaml
import requests
import json
import os
import time
import shutil
import pathlib


class AuraManager:
    def __init__(self):
        # load config
        with open("config.yaml", "r") as config_file:
            self.config = yaml.safe_load(config_file)

        print("config values: ", self.config)

        self.email = self.config["accounts"][0]["email"]
        self.password = self.config["accounts"][0]["password"]
        self.base_file_path = self.config["base_file_path"]
        self.debug_file_path = self.config["debug_file_path"]

        # image_path = pathlib.Path(self.base_file_path)
        # image_path.mkdir(parents=True, exist_ok=True)

        debug_path = pathlib.Path(self.debug_file_path)
        debug_path.mkdir(parents=True, exist_ok=True)

        self.login()

    def login(self):
        # define URLs and payload format
        login_url = "https://api.pushd.com/v5/login.json"
        login_payload = {
            "identifier_for_vendor": "does-not-matter",
            "client_device_id": "does-not-matter",
            "app_identifier": "com.pushd.Framelord",
            "locale": "en",
            "user": {"email": self.email, "password": self.password},
        }

        print(f"Logging into Aura")

        # make login request with credentials
        self.session = requests.Session()
        r = self.session.post(login_url, json=login_payload)

        if r.status_code != 200:
            print("Login Error: Check your credentials")
            return 0

        print("Login Success")

        # get json and update user and auth token headers for next request
        json_data = r.json()
        self.session.headers.update(
            {
                "X-User-Id": json_data["result"]["current_user"]["id"],
                "X-Token-Auth": json_data["result"]["current_user"]["auth_token"],
            }
        )

    def list_assets(self, frame_id, write_to_file=False):
        print(f"Listing assets for frame {frame_id}")
        frame_url = f"https://api.pushd.com/v5/frames/{frame_id}/assets.json?side_load_users=false"
        r = self.session.get(frame_url)
        json_data = json.loads(r.text)

        # check to make sure the frame assets array exists
        if "assets" not in json_data:
            print("Download Error: No images returned from this Aura Frame.")
            write_to_file = True
            return 0

        if write_to_file:
            with open(f"{self.debug_file_path}/{frame_id}_assets.json", "w") as f:
                json.dump(json_data, f)

        print(f"Found {len(json_data['assets'])} assets")

        return json_data["assets"]

    def download_assets(self, frame_id, assets, videos_only=False):
        print(f"Downloading {len(assets)} photos for frame {frame_id}")
        counter = 0
        skipped = 0

        image_path = pathlib.Path(self.base_file_path, frame_id)
        image_path.mkdir(parents=True, exist_ok=True)

        for item in assets:
            # print(f"{counter}: Checking {item['id']}")
            counter += 1

            try:
                is_video = False

                # get file name and construct URL
                if (
                    item["video_file_name"] is not None
                    and item["video_file_name"] != "null"
                ):
                    file_name = item["video_file_name"]
                    url = item["video_url"]
                    is_video = True
                else:
                    file_name = item["file_name"]
                    url = f"https://imgproxy.pushd.com/{item['user_id']}/{file_name}"

                if videos_only and not is_video:
                    print(f"{counter}: Skipping {item['id']}, not a video")
                    skipped += 1
                    continue

                # construct new filename
                new_filename = item["id"] + os.path.splitext(file_name)[1]
                file_to_write = os.path.join(image_path, new_filename)

                # check if file exists and skip it if so
                if os.path.isfile(file_to_write):
                    print(f"{counter}: Skipping {item['id']}, already downloaded")
                    skipped += 1
                    continue

                # Get the photo from the url
                print(f"{counter}: Downloading {new_filename}")
                response = requests.get(url, stream=True)

                # write to a file
                with open(file_to_write, "wb") as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                del response

                # wait a bit to avoid throttling
                time.sleep(2)

            except KeyboardInterrupt:
                print("Exiting from keyboard interrupt")
                break

            except Exception as e:
                print(f"Errored out on item: {counter}, probably due to throttling")
                print(str(e))
                time.sleep(10)

        return counter - skipped

    def start_batch_download(self, videos_only=False):
        for frame in self.config["frames"]:
            assets = self.list_assets(frame["frame_id"])
            total = self.download_assets(frame["frame_id"], assets, videos_only)
            print(f"Downloaded {total} photos")
