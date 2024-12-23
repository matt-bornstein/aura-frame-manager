from auramanager import AuraManager
import os
import json
from imgcat import imgcat
import cv2

def review_files():
    # read the reviewed-files.json file
    with open("debug/reviewed-files.json", "r") as f:
        data = json.load(f)
        keep_files = data["keep_files"]
        delete_files = data["delete_files"]
    
    deleted_files = len(os.listdir("/Users/mb/Documents/aura/nov 2024 export/deleted"))
    files_in_folder = len(os.listdir("/Users/mb/Documents/aura/nov 2024 export"))

    # print the total number of files already reviewed
    # then print the total number of files to review
    # and print the number of files left to review
    print(f"Already reviewed {deleted_files + len(keep_files) + len(delete_files)} files")
    print(f"Files left to review: {files_in_folder - (len(keep_files) + len(delete_files))}")
    print()

    # process all files in the folder "~/Documents/aura/nov 2024 export"
    # only process the files that are not in the keep_files or delete_files lists
    # for each file, show it in the terminal using the imgcat library (https://github.com/wookayin/python-imgcat)
    # and prompt the user if they want to keep the file
    # if they want to keep the file, add the file name to the keep_files list
    # if they don't want to keep the file, add the file name to the delete_files list
    # after processing each file, combine the keep_files and delete_files lists into a dictionary and write it to a json file
    for file in os.listdir("/Users/mb/Documents/aura/nov 2024 export"):
        if os.path.isfile(f"/Users/mb/Documents/aura/nov 2024 export/{file}") and file not in keep_files and file not in delete_files:
            # if it's a video, extract the first frame and show it
            if file.endswith(".mp4"):
                video_path = f"/Users/mb/Documents/aura/nov 2024 export/{file}"
                # Read the video and extract first frame
                video = cv2.VideoCapture(video_path)
                ret, frame = video.read()
                if ret:
                    # Convert BGR to RGB (cv2 uses BGR by default)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    imgcat(frame_rgb)
                    video.release()
            # if it's an image, show it
            else:
                with open(f"/Users/mb/Documents/aura/nov 2024 export/{file}", "rb") as f:
                    imgcat(f)
            
            # prompt the user if they want to keep the file
            print(f"Files left to review: {files_in_folder - (len(keep_files) + len(delete_files))}")
            user_input = input(f"{file} | Do you want to keep this file? (y or enter to keep, n to delete): ")
            if user_input == "y" or user_input == "":
                print(f"Keeping {file}")
                keep_files.append(file)
            else:
                print(f"Deleting {file}")
                delete_files.append(file)
            
            # print a blank line to the terminal
            print()

            # combine keep_files and delete_files into a dictionary
            files_dict = {
                "keep_files": keep_files,
                "delete_files": delete_files
            }
            # write the dictionary to a json file
            with open("debug/reviewed-files.json", "w") as f:
                json.dump(files_dict, f, indent=4)

def remove_files():
    # read the reviewed-files.json file
    with open("debug/reviewed-files.json", "r") as f:
        data = json.load(f)
        keep_files = data["keep_files"]
        delete_files = data["delete_files"]
    
    delete_files_new = []

    # move the files in the delete_files list from the folder "~/Documents/aura/nov 2024 export"
    # to the folder "~/Documents/aura/nov 2024 export/deleted"
    for file in delete_files:
        try:
            os.rename(f"/Users/mb/Documents/aura/nov 2024 export/{file}", f"/Users/mb/Documents/aura/nov 2024 export/deleted/{file}")
            print(f"Moved {file} to deleted folder")
        except Exception as e:
            print(f"Error moving file {file}: {e}")
            delete_files_new.append(file)
    
    # write the updated delete_files list to the reviewed-files.json file
    with open("debug/reviewed-files.json", "w") as f:
        json.dump({"keep_files": keep_files, "delete_files": delete_files_new}, f, indent=4)

# this is a grab bag right now, not a working function
def prep_assets_to_review():
    # read all json files in debug folder and combine the assets arrays into one array
    # assets_all = []
    # for file in os.listdir("debug"):
    #     if file.endswith("_assets.json"):
    #         # read the json file
    #         print(f"Reading {file}")
    #         with open(f"debug/{file}", "r") as f:
    #             data = json.load(f)
    #             # print the data using json dump
    #             # print(json.dumps(data, indent=4))
    #             assets = data["assets"]
    #             assets_all.extend(assets)

    # # filter assets_all to only include videos
    # # only keep the fields id, video_url, file_name, video_file_name
    # assets_all_videos = [
    #     {
    #         "id": asset["id"],
    #         "video_url": asset["video_url"],
    #         "file_name": asset["file_name"],
    #         "video_file_name": asset["video_file_name"],
    #     }
    #     for asset in assets_all
    #     if asset["video_file_name"]
    # ]

    # # write the filtered assets array to a file
    # with open("debug/assets_all_videos.json", "w") as f:
    #     json.dump(assets_all_videos, f)

    # read the assets_all_videos.json file and delete the files from the folder "~/Documents/aura/nov 2024 export"
    # delete_count = 0
    # error_count = 0
    # with open("debug/assets_all_videos.json", "r") as f:
    #     data = json.load(f)
    #     # for each asset, delete the file from the folder "~/Documents/aura/nov 2024 export"
    #     for asset in data:
    #         extension = asset["file_name"].split(".")[-1]
    #         try:
    #             os.remove(f"~/Documents/aura/nov 2024 export/{asset['id']}.{extension}")
    #             delete_count += 1
    #         except Exception as e:
    #             print(f"Error deleting file {asset['id']}.{extension}: {e}")
    #             error_count += 1

    # print(f"Deleted {delete_count} files")
    # print(f"Errors deleting {error_count} files")
    pass

def main():
    aura = AuraManager()
    # aura.start_batch_download(videos_only=True)
    # aura.list_assets_all(True)
    # aura.list_assets(aura.config["frames"][0]["frame_id"], True)
    aura.fit_assets(aura.config["frames"][0]["frame_id"])
    
    # review_files()
    # remove_files()


if __name__ == "__main__":
    main()
