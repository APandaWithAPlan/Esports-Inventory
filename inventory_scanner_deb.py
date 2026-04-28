import os
import uuid
import nfc
import ndef
import time
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def get_user(user_id: str):
    res = supabase.table("Users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None

def get_item(item_uuid: str):
    res = supabase.table("Inventory").select("*").eq("id", item_uuid).execute()
    return res.data[0] if res.data else None

def register_user(user_id: str):
    print(f"\n[!] User ID {user_id} not found.")
    name = input("Enter Name for new User registration: ")
    if name:
        supabase.table("Users").insert({"id": user_id, "name": name, "currently_renting": []}).execute()
        print(f"User {name} registered!")
        return {"id": user_id, "name": name, "currently_renting": []}
    return None

def handle_existing_item(item):
    print(f"\n--- Item Details ---")
    print(f"Name: {item['name']}")
    
    renter_res = supabase.table("Users").select("*").contains("currently_renting", [item['id']]).execute()
    renter = renter_res.data[0] if renter_res.data else None

    if renter:
        print(f"STATUS: [ RENTED ] to {renter['name']}")
        print("1. Return Item (Check-in)")
        print("2. Do Nothing")
        
        choice = input("Select an option: ")
        if choice == "1":

            new_list = [i for i in renter['currently_renting'] if i != item['id']]
            supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
            
            supabase.table("Inventory").update({
                "is_rented": False
            }).eq("id", item['id']).execute()
            
            print(f"Item '{item['name']}' returned. Status updated in Inventory.")
            
    else:
        print(f"STATUS: [ AVAILABLE ] (Last Renter: {item.get('last_rented_person', 'None')})")
        print("1. Rent out to User")
        print("2. Do Nothing")

        choice = input("Select an option: ")
        if choice == "1":
            print("\n[WAIT] Please scan the USER CARD now...")
            u_id = input("User ID: ")
            if (len(u_id) > 9):
                u_id = u_id[1:9]

            user = get_user(u_id) or register_user(u_id)
            
            if user:
                current_items = user.get('currently_renting') or []
                if item['id'] not in current_items:
                    current_items.append(item['id'])
                    supabase.table("Users").update({"currently_renting": current_items}).eq("id", user['id']).execute()
                    
                    supabase.table("Inventory").update({
                        "is_rented": True,
                        "last_rented_person": user['name'] 
                    }).eq("id", item['id']).execute()
                    
                    print(f"Success: {item['name']} rented to {user['name']}.")
                else:
                    print("User already has this item checked out!")

def process_tag(tag):
    tag_uuid = None
    if tag.ndef and len(tag.ndef.records) > 0:
        for record in tag.ndef.records:
            if isinstance(record, ndef.TextRecord):
                tag_uuid = record.text
                break

    if tag_uuid:
        item = get_item(tag_uuid)
        if item:
            handle_existing_item(item)
        else:
            print(f"Unrecognized UUID: {tag_uuid}")
            if input("Register as new item? (y/n): ") == 'y':
                flash_new_item(tag, tag_uuid)
    else:
        flash_new_item(tag)

def flash_new_item(tag, existing_uuid=None):
    new_uuid = existing_uuid or str(uuid.uuid4())
    name = input("Enter name for NEW inventory item: ")
    if not name: return

    try:
        if tag.ndef:
            tag.ndef.records = [ndef.TextRecord(new_uuid)]
            supabase.table("Inventory").insert({"id": new_uuid, "name": name}).execute()
            print("Tag flashed and Item saved.")
    except Exception as e:
        print(f"Flashing error: {e}")

def main():
    clf = None
    # Common connection paths for Raspberry Pi
    # tty:serial0 -> Standard UART pinout on Raspberry Pi
    # usb -> Standard USB connection
    connection_paths = ['tty:serial0', 'usb']
    
    for path in connection_paths:
        try:
            print(f"Attempting to connect to NFC reader via {path}...")
            clf = nfc.ContactlessFrontend(path)
            if clf:
                print(f"Successfully connected via {path}.")
                break
        except IOError:
            continue
            
    if not clf:
        print("Hardware Error: Could not connect to NFC reader. Check wiring, permissions, or raspi-config.")
        return

    try:
        print("\nInventory System Live. Scan NTAG215 to begin.")
        while True:
            tag = clf.connect(rdwr={'on-connect': lambda tag: False})
            if tag:
                process_tag(tag)
                print("\nReady...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nClosing...")
    finally:
        clf.close()

if __name__ == "__main__":
    main()