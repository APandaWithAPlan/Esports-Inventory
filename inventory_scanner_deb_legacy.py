import os
import uuid
import nfc
import ndef
import time
import threading
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
from datetime import datetime
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
        self.root.geometry("1024x768") 
        
        # Base background - Dark Blue
        self.root.configure(bg="#0f172a")

        self.cart = [] # Store items to be rented together

        # --- Layout Setup ---
        # Left side: Logs (Blue Theme)
        self.left_frame = tk.Frame(root, bg="#1e3a8a", bd=5)
        self.left_frame.pack(side=tk.LEFT, expand=True, fill='both', padx=(10, 5), pady=10)
        
        tk.Label(self.left_frame, text="System Logs", font=("Consolas", 14, "bold"), bg="#1e3a8a", fg="white").pack(pady=(5, 5))
        
        self.text_area = scrolledtext.ScrolledText(self.left_frame, wrap=tk.WORD, state='disabled', font=("Consolas", 11), bg="#eff6ff", fg="#0f172a")
        self.text_area.pack(expand=True, fill='both', padx=5, pady=5)

        # Right side: Cart UI (Red Theme, Increased Space)
        self.right_frame = tk.Frame(root, bg="#7f1d1d", bd=5, width=450) # Wider cart area
        self.right_frame.pack_propagate(False) # Forces the frame to keep its width
        self.right_frame.pack(side=tk.RIGHT, fill='both', padx=(5, 10), pady=10)
        
        tk.Label(self.right_frame, text="Rental Cart", font=("Consolas", 18, "bold"), bg="#7f1d1d", fg="white").pack(pady=(10, 5))
        
        self.cart_listbox = tk.Listbox(self.right_frame, font=("Consolas", 14), bg="#fef2f2", fg="#7f1d1d", selectbackground="#f87171")
        # fill='both' allows it to take up the newly allocated space
        self.cart_listbox.pack(expand=True, fill='both', padx=10, pady=10) 
        
        # Buttons with corresponding colors
        self.checkout_btn = tk.Button(self.right_frame, text="Checkout Cart", command=self.checkout_cart_thread, bg="#1d4ed8", fg="white", font=("Consolas", 14, "bold"), height=2)
        self.checkout_btn.pack(fill='x', padx=10, pady=(0, 5))

        self.clear_btn = tk.Button(self.right_frame, text="Clear Cart", command=self.clear_cart, bg="#b91c1c", fg="white", font=("Consolas", 14, "bold"), height=2)
        self.clear_btn.pack(fill='x', padx=10, pady=(0, 10))

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

    # --- Cart Operations ---
    def add_to_cart(self, item):
        if any(cart_item['id'] == item['id'] for cart_item in self.cart):
            self.log(f"[*] {item['name']} is already in the cart!")
            return
        self.cart.append(item)
        self.cart_listbox.insert(tk.END, item['name'])
        self.log(f"[+] Added '{item['name']}' to cart.")

    def clear_cart(self):
        self.cart.clear()
        self.cart_listbox.delete(0, tk.END)
        self.log("[-] Cart cleared.")

    def checkout_cart_thread(self):
        if not self.cart:
            messagebox.showwarning("Empty Cart", "The cart is empty! Scan items first.")
            return
        # Run checkout in background to not freeze UI during DB operations
        threading.Thread(target=self._process_checkout, daemon=True).start()

    def _process_checkout(self):
        self.log("\n[WAIT] Waiting for user input for Checkout...")
        u_id = self.ask_string("User ID Scan", f"Checking out {len(self.cart)} items.\nPlease enter or scan the USER CARD ID now:")
        
        if not u_id:
            self.log("Checkout cancelled.")
            return

        if len(u_id) > 9:
            u_id = u_id[1:9]

        user = get_user(u_id) or register_user(u_id)
        if not user:
            self.log("Checkout failed: Could not fetch/register user.")
            return

        current_items = user.get('currently_renting') or []
        new_item_ids = [item['id'] for item in self.cart if item['id'] not in current_items]
        
        if not new_item_ids:
            self.log("All items in cart are already checked out to this user.")
            self.root.after(0, self.clear_cart)
            return

        # 1. Update User's currently_renting list once
        current_items.extend(new_item_ids)
        supabase.table("Users").update({"currently_renting": current_items}).eq("id", user['id']).execute()

        # 2. Update each Inventory item
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in self.cart:
            if item['id'] in new_item_ids:
                history = item.get('rental_history') or []
                history.append(f"{user['name']}/{current_time}/PENDING")
                
                supabase.table("Inventory").update({
                    "is_rented": True,
                    "last_rented_person": user['name'],
                    "rental_history": history
                }).eq("id", item['id']).execute()
        
        self.log(f"\n[SUCCESS] Checked out {len(new_item_ids)} item(s) to {user['name']}.")
        self.root.after(0, self.clear_cart)


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
        
        # Returns are still handled individually immediately upon scanning
        choice = gui.ask_yes_no("Return Item", f"Item '{item['name']}' is rented by {renter['name']}.\n\nProcess a Return (Check-in)?")
        if choice:
            condition = gui.ask_string("Item Condition", f"Update condition of '{item['name']}' on return?\n(e.g., Good, Scratched, Damaged):")
            if condition is None: 
                condition = "Not specified"

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            history = item.get('rental_history') or []
            if history:
                history[-1] = history[-1].replace("PENDING", current_time)

            new_list = [i for i in renter['currently_renting'] if i != item['id']]
            supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
            
            update_payload = {
                "is_rented": False,
                "rental_history": history
            }
            if condition != "":
                update_payload["condition"] = condition

            supabase.table("Inventory").update(update_payload).eq("id", item['id']).execute()
            gui.log(f"Item '{item['name']}' returned. Condition logged as: {condition}.")
            
    else:
        current_condition = item.get('condition', 'Not specified')
        gui.log(f"STATUS: [ AVAILABLE ] (Last Renter: {item.get('last_rented_person', 'None')})")
        gui.log(f"CONDITION: {current_condition}")
        
        # Instead of asking for a User immediately, we add to Cart
        choice = gui.ask_yes_no("Add to Cart", f"Item '{item['name']}' is available.\n\nAdd to checkout cart?")
        if choice:
            gui.root.after(0, gui.add_to_cart, item)

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
            supabase.table("Inventory").insert({
                "id": new_uuid, 
                "name": name,
                "condition": "New", 
                "rental_history": []
            }).execute()
            gui.log(f"Tag flashed and Item '{name}' saved.")
    except Exception as e:
        gui.log(f"Flashing error: {e}")

# --- Background NFC Hardware Loop ---
def nfc_worker():
    clf = None
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
    root = tk.Tk()
    gui = AppGUI(root)
    worker_thread = threading.Thread(target=nfc_worker, daemon=True)
    worker_thread.start()
    root.mainloop()