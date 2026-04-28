import os
import uuid
import nfc
import ndef
import time
import threading
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# --- Thread-Safe GUI Helper ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NFC Inventory Management System")
        self.root.geometry("650x450")
        
        self.text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state='disabled', font=("Consolas", 10))
        self.text_area.pack(expand=True, fill='both', padx=10, pady=10)

        # Event flags to pause the background thread while waiting for UI input
        self.event = threading.Event()
        self.result = None

    def log(self, msg):
        self.root.after(0, self._log_gui, msg)

    def _log_gui(self, msg):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, str(msg) + "\n")
        self.text_area.see(tk.END)
        self.text_area.configure(state='disabled')

    def ask_string(self, title, prompt):
        self.event.clear()
        self.root.after(0, self._ask_string_gui, title, prompt)
        self.event.wait()
        return self.result

    def _ask_string_gui(self, title, prompt):
        self.result = simpledialog.askstring(title, prompt, parent=self.root)
        self.event.set()

    def ask_yes_no(self, title, prompt):
        self.event.clear()
        self.root.after(0, self._ask_yes_no_gui, title, prompt)
        self.event.wait()
        return self.result

    def _ask_yes_no_gui(self, title, prompt):
        self.result = messagebox.askyesno(title, prompt, parent=self.root)
        self.event.set()

# --- Core Logic ---
def get_user(user_id: str):
    res = supabase.table("Users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None

def get_item(item_uuid: str):
    res = supabase.table("Inventory").select("*").eq("id", item_uuid).execute()
    return res.data[0] if res.data else None

def register_user(user_id: str):
    gui.log(f"\n[!] User ID {user_id} not found.")
    name = gui.ask_string("Register New User", "Enter Name for new User registration:")
    if name:
        supabase.table("Users").insert({"id": user_id, "name": name, "currently_renting": []}).execute()
        gui.log(f"User {name} registered!")
        return {"id": user_id, "name": name, "currently_renting": []}
    return None

def handle_existing_item(item):
    gui.log(f"\n--- Item Details ---")
    gui.log(f"Name: {item['name']}")
    
    renter_res = supabase.table("Users").select("*").contains("currently_renting", [item['id']]).execute()
    renter = renter_res.data[0] if renter_res.data else None

    if renter:
        gui.log(f"STATUS: [ RENTED ] to {renter['name']}")
        
        choice = gui.ask_yes_no("Return Item", f"Item '{item['name']}' is rented by {renter['name']}.\n\nDo you want to process a Return (Check-in)?")
        if choice:
            # Added condition prompt
            condition = gui.ask_string("Item Condition", f"Enter condition of '{item['name']}' on return\n(e.g., Good, Scratched, Damaged):")
            if condition is None: 
                condition = "Not specified"

            new_list = [i for i in renter['currently_renting'] if i != item['id']]
            supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
            
            supabase.table("Inventory").update({
                "is_rented": False,
                "condition": condition # Condition updated here
            }).eq("id", item['id']).execute()
            
            gui.log(f"Item '{item['name']}' returned. Condition logged as: {condition}.")
            
    else:
        gui.log(f"STATUS: [ AVAILABLE ] (Last Renter: {item.get('last_rented_person', 'None')})")
        
        choice = gui.ask_yes_no("Rent Item", f"Item '{item['name']}' is available.\n\nRent out to a user?")
        if choice:
            gui.log("\n[WAIT] Waiting for user input...")
            u_id = gui.ask_string("User ID Scan", "Please enter or scan the USER CARD ID now:")
            
            if u_id:
                if len(u_id) > 9:
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
                        
                        gui.log(f"Success: {item['name']} rented to {user['name']}.")
                    else:
                        gui.log("User already has this item checked out!")

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
            gui.log(f"Unrecognized UUID: {tag_uuid}")
            if gui.ask_yes_no("New Item", "Unrecognized Tag.\nRegister as a new inventory item?"):
                flash_new_item(tag, tag_uuid)
    else:
        flash_new_item(tag)

def flash_new_item(tag, existing_uuid=None):
    new_uuid = existing_uuid or str(uuid.uuid4())
    name = gui.ask_string("Register Item", "Enter name for NEW inventory item:")
    if not name: 
        gui.log("Registration cancelled.")
        return

    try:
        if tag.ndef:
            tag.ndef.records = [ndef.TextRecord(new_uuid)]
            supabase.table("Inventory").insert({"id": new_uuid, "name": name}).execute()
            gui.log(f"Tag flashed and Item '{name}' saved.")
    except Exception as e:
        gui.log(f"Flashing error: {e}")

# --- Background NFC Hardware Loop ---
def nfc_worker():
    clf = None
    # Common connection paths for Raspberry Pi
    # tty:serial0 -> Standard UART pinout on Raspberry Pi
    # usb -> Standard USB connection
    connection_paths = ['tty:serial0', 'usb']
    
    for path in connection_paths:
        try:
            gui.log(f"Attempting to connect to NFC reader via {path}...")
            clf = nfc.ContactlessFrontend(path)
            if clf:
                gui.log(f"Successfully connected via {path}.")
                break
        except IOError:
            continue
            
    if not clf:
        gui.log("Hardware Error: Could not connect to NFC reader. Check wiring, permissions, or raspi-config.")
        return

    try:
        gui.log("\nInventory System Live. Scan NTAG215 to begin.")
        while True:
            tag = clf.connect(rdwr={'on-connect': lambda tag: False})
            if tag:
                process_tag(tag)
                gui.log("\nReady for next tag...")
            time.sleep(1)
    except Exception as e:
        gui.log(f"\nClosing or Error: {e}")
    finally:
        if clf:
            clf.close()

if __name__ == "__main__":
    # Setup the Tkinter Root
    root = tk.Tk()
    
    # Initialize Global GUI controller
    gui = AppGUI(root)
    
    # Start NFC scanning in a background daemon thread 
    # (Daemon ensures the thread dies when you close the GUI window)
    worker_thread = threading.Thread(target=nfc_worker, daemon=True)
    worker_thread.start()
    
    # Start the Tkinter main loop
    root.mainloop()