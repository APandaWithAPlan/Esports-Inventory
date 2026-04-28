import os
import uuid
import nfc
import ndef
import time
import threading
import queue
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
from supabase import create_client, Client
from dotenv import load_dotenv

# --- Database Setup ---
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

def register_user_db(user_id: str, name: str):
    supabase.table("Users").insert({"id": user_id, "name": name, "currently_renting": []}).execute()
    return {"id": user_id, "name": name, "currently_renting": []}


# --- Responsive GUI Application ---
class InventoryKiosk:
    def __init__(self, root):
        self.root = root
        self.root.title("NFC Inventory Kiosk")
        self.root.geometry("650x500")
        
        # UI Elements
        self.status_var = tk.StringVar(value="Initializing Hardware...")
        self.header = tk.Label(root, textvariable=self.status_var, font=("Helvetica", 16, "bold"), pady=15)
        self.header.pack()
        
        self.log_area = scrolledtext.ScrolledText(root, width=70, height=20, state='disabled', font=("Courier", 10))
        self.log_area.pack(padx=20, pady=10)
        
        # Communication Queues
        self.read_queue = queue.Queue()
        self.write_queue = queue.Queue()
        
        # Start background NFC Thread
        self.nfc_thread = threading.Thread(target=self.nfc_hardware_loop, daemon=True)
        self.nfc_thread.start()
        
        # Start polling the queue to update UI
        self.root.after(100, self.process_ui_queue)

    def log(self, message):
        """Safely print messages to the GUI text box."""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"> {message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def nfc_hardware_loop(self):
        """Runs in the background, handling the blocking NFC connection."""
        clf = None
        for path in ['tty:serial0', 'usb']:
            try:
                clf = nfc.ContactlessFrontend(path)
                break
            except IOError:
                continue
                
        if not clf:
            self.status_var.set("Hardware Error! Check NFC Reader.")
            self.log("ERROR: Could not connect to NFC hardware.")
            return

        self.status_var.set("System Live. Tap an item to scan.")
        self.log("NFC Scanner initialized and waiting...")

        while True:
            # 1. Check if the UI requested a tag to be formatted/flashed
            if not self.write_queue.empty():
                write_data = self.write_queue.get()
                self.status_var.set("FLASHING: Hold tag to reader...")
                
                def on_connect_write(tag):
                    if tag.ndef:
                        tag.ndef.records = [ndef.TextRecord(write_data['uuid'])]
                        return True
                    return False
                
                clf.connect(rdwr={'on-connect': on_connect_write})
                self.log(f"Successfully flashed tag with UUID: {write_data['uuid']}")
                self.status_var.set("System Live. Tap an item to scan.")
                time.sleep(1)
                continue

            # 2. Normal Read Mode
            def on_connect_read(tag):
                tag_uuid = None
                if tag.ndef and len(tag.ndef.records) > 0:
                    for record in tag.ndef.records:
                        if isinstance(record, ndef.TextRecord):
                            tag_uuid = record.text
                            break
                # Send the result to the UI thread
                self.read_queue.put(tag_uuid)
                return True

            # The 'terminate' argument ensures the scanner stops blocking 
            # immediately if the UI needs to write a new tag.
            clf.connect(
                rdwr={'on-connect': on_connect_read},
                terminate=lambda: not self.write_queue.empty()
            )
            time.sleep(0.5) # Debounce to prevent rapid double-scans

    def process_ui_queue(self):
        """Checks if the background thread has passed along a scanned tag."""
        try:
            tag_uuid = self.read_queue.get_nowait()
            self.handle_scanned_tag(tag_uuid)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_ui_queue)

    def handle_scanned_tag(self, tag_uuid):
        if not tag_uuid:
            if messagebox.askyesno("Blank Tag", "This tag is blank. Register as new item?"):
                self.register_new_item()
            return

        item = get_item(tag_uuid)
        if item:
            self.process_existing_item(item)
        else:
            self.log(f"Unrecognized UUID: {tag_uuid}")
            if messagebox.askyesno("Unknown Tag", "This tag is not in the database. Register it?"):
                self.register_new_item(tag_uuid)

    def process_existing_item(self, item):
        renter_res = supabase.table("Users").select("*").contains("currently_renting", [item['id']]).execute()
        renter = renter_res.data[0] if renter_res.data else None

        if renter:
            if messagebox.askyesno("Check In", f"[{item['name']}] is currently checked out to {renter['name']}.\n\nReturn this item?"):
                new_list = [i for i in renter['currently_renting'] if i != item['id']]
                supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
                supabase.table("Inventory").update({"is_rented": False}).eq("id", item['id']).execute()
                self.log(f"RETURNED: {item['name']}")
                
        else:
            last_renter = item.get('last_rented_person', 'None')
            if messagebox.askyesno("Check Out", f"[{item['name']}] is available. (Last renter: {last_renter})\n\nCheck out this item?"):
                self.process_rental(item)

    def process_rental(self, item):
        u_id = simpledialog.askstring("User Identification", "Scan or enter the User ID:")
        if not u_id:
            return # User cancelled
            
        if len(u_id) > 9:
            u_id = u_id[1:9]

        user = get_user(u_id)
        if not user:
            name = simpledialog.askstring("New User", f"User ID '{u_id}' not found.\nEnter Name to register new user:")
            if name:
                user = register_user_db(u_id, name)
                self.log(f"Registered new user: {name}")
            else:
                return

        if user:
            current_items = user.get('currently_renting') or []
            if item['id'] not in current_items:
                current_items.append(item['id'])
                supabase.table("Users").update({"currently_renting": current_items}).eq("id", user['id']).execute()
                supabase.table("Inventory").update({
                    "is_rented": True,
                    "last_rented_person": user['name'] 
                }).eq("id", item['id']).execute()
                
                self.log(f"RENTED: {item['name']} -> {user['name']}.")
            else:
                messagebox.showinfo("Notice", "User already has this item checked out.")

    def register_new_item(self, existing_uuid=None):
        new_uuid = existing_uuid or str(uuid.uuid4())
        name = simpledialog.askstring("New Item", "Enter the name for this new inventory item:")
        
        if name:
            try:
                supabase.table("Inventory").insert({"id": new_uuid, "name": name}).execute()
                self.log(f"Database updated with new item: {name}")
                
                if not existing_uuid:
                    self.log("Awaiting tag tap to flash new UUID...")
                    self.write_queue.put({'uuid': new_uuid})
                    
            except Exception as e:
                self.log(f"Database Error: {e}")
                messagebox.showerror("Error", "Failed to save item to database.")

if __name__ == "__main__":
    # Tkinter must be run on the main thread
    root = tk.Tk()
    app = InventoryKiosk(root)
    root.mainloop()