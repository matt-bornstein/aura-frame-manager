from auramanager import AuraManager

def main():
    aura = AuraManager()
    aura.start_batch_download(videos_only=True)
    # aura.list_assets("e49b1380-70dd-4e19-97b4-2b95e269a8d9", True)

if __name__ == "__main__":
    main()