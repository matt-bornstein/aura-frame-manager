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
                json.dump(json_data, f, indent=4)

        print(f"Found {len(json_data['assets'])} assets")

        return json_data["assets"]

    def download_assets(self, frame_id, assets, videos_only=False):
        print(f"Downloading {len(assets)} photos for frame {frame_id}")
        counter = 0
        skipped = 0

        image_path = pathlib.Path(self.base_file_path, frame_id)
        image_path.mkdir(parents=True, exist_ok=True)

        for item in assets:
            counter += 1
            # print(f"{counter}: Checking {item['id']}")

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

    def list_assets_all(self, write_to_file=False):
        # assets_all = []
        for frame in self.config["frames"]:
            assets = self.list_assets(frame["frame_id"], write_to_file)
            # assets_all.append({
            #     "frame": frame["frame_id"],
            #     "assets": assets
            # })

        # return assets_all

    def crop_asset(self, asset, fit=True, params=None):
        # POST to https://api.pushd.com/v5/assets/crop.json
        # example payload:
        # id is the id field from assets array
        # user_id is the user_id field from assets array, not sure if it's needed
        # 4284 is the width of the image
        # 5712 is the height of the image
        # {
        #     "id": "a8e3ed8c-b04d-11ef-9ab8-0affcf9d92af",
        #     "local_identifier": null,
        #     "user_id": "85feec8c-7d7c-11ed-a975-0e4972f5035b",
        #     "rotation_cw": 0,
        #     "user_landscape_16_10_rect": null,
        #     "user_landscape_rect": "0,0,4284,5712",
        #     "user_portrait_4_5_rect": null,
        #     "user_portrait_rect": null
        # }
        print(f"Cropping {asset['id']}, fit={fit}")

        url = "https://api.pushd.com/v5/assets/crop.json"
        payload = {
            "id": asset["id"],
            "local_identifier": None,
            "user_id": asset["user_id"],
        }

        if fit:
            payload.update(
                {
                    "rotation_cw": 0,
                    "user_landscape_16_10_rect": None,
                    "user_landscape_rect": f"0,0,{asset['width']},{asset['height']}",
                    "user_portrait_4_5_rect": None,
                    "user_portrait_rect": None,
                }
            )
        else:
            payload.update(params)

        r = self.session.post(url, json=payload)

        if r.status_code != 200:
            print(f"Crop Error: {r.text}")
            return 0

        print("Crop Success")

        return json.loads(r.text)["asset"]

    def fit_assets(self, frame_id):
        assets = self.list_assets(frame_id)
        print(f"Found {len(assets)} assets for frame {frame_id}")

        counter = 0
        for asset in assets:
            # check for portrait and auto-crop
            if (
                asset["width"] < asset["height"]
                and asset["auto_portrait_4_5_rect"] is not None
            ):
                print(
                    f"Fitting {asset['id']} (width={asset['width']}, height={asset['height']}, auto_rect={asset['auto_portrait_4_5_rect']})"
                )
                self.crop_asset(asset, fit=True)
                counter += 1
            else:
                print(
                    f"Skipping {asset['id']} (width={asset['width']}, height={asset['height']}, auto_rect={asset['auto_portrait_4_5_rect']})"
                )

        print(f"Fitted {counter} assets")

    def start_batch_download(self, videos_only=False):
        for frame in self.config["frames"]:
            assets = self.list_assets(frame["frame_id"])
            total = self.download_assets(frame["frame_id"], assets, videos_only)
            print(f"Downloaded {total} photos")
