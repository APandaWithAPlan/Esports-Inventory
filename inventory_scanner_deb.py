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

        self.cart = [] # Store items to be rented together
        self.is_dark_mode = True # Default to Dark Mode
        self.current_admin = None # Track logged-in admin

        # --- Theme Definitions ---
        self.themes = {
            "dark": {
                "main_bg": "#0f172a",
                "left_bg": "#1e3a8a",
                "left_fg": "white",
                "text_bg": "#020617",     
                "text_fg": "#e2e8f0",     
                "right_bg": "#7f1d1d",
                "right_fg": "white",
                "list_bg": "#450a0a",     
                "list_fg": "#fecaca",     
                "list_sel": "#991b1b",    
                "btn_checkout_bg": "#1d4ed8",
                "btn_clear_bg": "#b91c1c",
                "btn_view_bg": "#d97706", # Amber for View button
                "btn_toggle_bg": "#334155",
                "btn_toggle_fg": "white",
                "admin_logged_in": "#34d399", 
                "admin_logged_out": "#f87171" 
            },
            "light": {
                "main_bg": "#f8fafc",
                "left_bg": "#dbeafe",
                "left_fg": "#1e3a8a",
                "text_bg": "#ffffff",     
                "text_fg": "#0f172a",     
                "right_bg": "#fee2e2",
                "right_fg": "#7f1d1d",
                "list_bg": "#ffffff",     
                "list_fg": "#0f172a",     
                "list_sel": "#fca5a5",    
                "btn_checkout_bg": "#3b82f6",
                "btn_clear_bg": "#ef4444",
                "btn_view_bg": "#f59e0b", # Amber for View button
                "btn_toggle_bg": "#cbd5e1",
                "btn_toggle_fg": "#0f172a",
                "admin_logged_in": "#059669", 
                "admin_logged_out": "#dc2626" 
            }
        }

        # --- Layout Setup ---
        # Left side: Logs
        self.left_frame = tk.Frame(root, bd=5)
        self.left_frame.pack(side=tk.LEFT, expand=True, fill='both', padx=(10, 5), pady=10)
        
        self.log_label = tk.Label(self.left_frame, text="System Logs", font=("Consolas", 14, "bold"))
        self.log_label.pack(pady=(5, 5))
        
        self.text_area = scrolledtext.ScrolledText(self.left_frame, wrap=tk.WORD, state='disabled', font=("Consolas", 11))
        self.text_area.pack(expand=True, fill='both', padx=5, pady=5)

        # Right side: Cart UI
        self.right_frame = tk.Frame(root, bd=5, width=450)
        self.right_frame.pack_propagate(False)
        self.right_frame.pack(side=tk.RIGHT, fill='both', padx=(5, 10), pady=10)
        
        # Theme Toggle Button
        self.toggle_btn = tk.Button(self.right_frame, text="☀️ Light Mode", command=self.toggle_theme, font=("Consolas", 12, "bold"))
        self.toggle_btn.pack(fill='x', padx=10, pady=(5, 0))

        # Admin UI
        self.admin_label = tk.Label(self.right_frame, text="Admin: Not Logged In", font=("Consolas", 14, "bold"))
        self.admin_label.pack(pady=(15, 5))

        self.login_btn = tk.Button(self.right_frame, text="Admin Login", command=self.prompt_login_thread, font=("Consolas", 14, "bold"), height=2)
        self.login_btn.pack(fill='x', padx=10, pady=(0, 15))

        self.cart_label = tk.Label(self.right_frame, text="Rental Cart", font=("Consolas", 18, "bold"))
        self.cart_label.pack(pady=(10, 5))
        
        self.cart_listbox = tk.Listbox(self.right_frame, font=("Consolas", 14))
        self.cart_listbox.pack(expand=True, fill='both', padx=10, pady=10) 
        
        # Buttons
        self.checkout_btn = tk.Button(self.right_frame, text="Checkout Cart", command=self.checkout_cart_thread, font=("Consolas", 14, "bold"), height=2)
        self.checkout_btn.pack(fill='x', padx=10, pady=(0, 5))

        self.clear_btn = tk.Button(self.right_frame, text="Clear Cart", command=self.clear_cart, font=("Consolas", 14, "bold"), height=2)
        self.clear_btn.pack(fill='x', padx=10, pady=(0, 5))

        self.view_rented_btn = tk.Button(self.right_frame, text="View Rented Items", command=self.view_rented_items_thread, font=("Consolas", 14, "bold"), height=2)
        self.view_rented_btn.pack(fill='x', padx=10, pady=(0, 10))

        # Apply the initial theme colors
        self.apply_theme()

        # Event flags to pause the background thread while waiting for UI input
        self.event = threading.Event()
        self.result = None

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        
        self.root.configure(bg=theme["main_bg"])
        
        self.left_frame.configure(bg=theme["left_bg"])
        self.log_label.configure(bg=theme["left_bg"], fg=theme["left_fg"])
        self.text_area.configure(bg=theme["text_bg"], fg=theme["text_fg"], insertbackground=theme["text_fg"])
        
        self.right_frame.configure(bg=theme["right_bg"])
        self.cart_label.configure(bg=theme["right_bg"], fg=theme["right_fg"])
        self.cart_listbox.configure(bg=theme["list_bg"], fg=theme["list_fg"], selectbackground=theme["list_sel"])
        
        self.checkout_btn.configure(bg=theme["btn_checkout_bg"], fg="white")
        self.clear_btn.configure(bg=theme["btn_clear_bg"], fg="white")
        self.view_rented_btn.configure(bg=theme["btn_view_bg"], fg="white")
        
        toggle_text = "☀️ Light Mode" if self.is_dark_mode else "🌙 Dark Mode"
        self.toggle_btn.configure(text=toggle_text, bg=theme["btn_toggle_bg"], fg=theme["btn_toggle_fg"])

        self.admin_label.configure(bg=theme["right_bg"])
        self._update_admin_ui_colors()

    def _update_admin_ui_colors(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        if self.current_admin:
            self.admin_label.configure(text=f"Admin: {self.current_admin['name']}", fg=theme["admin_logged_in"])
            self.login_btn.configure(text="Admin Logout", bg=theme["btn_clear_bg"], fg="white")
        else:
            self.admin_label.configure(text="Admin: Not Logged In", fg=theme["admin_logged_out"])
            self.login_btn.configure(text="Admin Login", bg=theme["btn_checkout_bg"], fg="white")

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

    # --- Admin Authentication ---
    def prompt_login_thread(self):
        threading.Thread(target=self._process_login, daemon=True).start()

    def _process_login(self):
        if self.current_admin:
            self.current_admin = None
            self.root.after(0, self._update_admin_ui_colors)
            self.log("\n[-] Admin logged out. System Locked.")
            return

        self.log("\n[WAIT] Waiting for Admin ID scan...")
        a_id = self.ask_string("Admin Login", "Please scan or enter Admin ID:")
        
        if not a_id:
            self.log("Login cancelled.")
            return

        if len(a_id) > 9:
            a_id = a_id[1:9]

        res = supabase.table("Admins").select("*").eq("id", a_id).execute()
        if res.data:
            self.current_admin = res.data[0]
            self.root.after(0, self._update_admin_ui_colors)
            self.log(f"\n[+] Admin '{self.current_admin['name']}' logged in successfully. System Unlocked.")
        else:
            self.log("\n[!] Login failed: Admin ID not found in database.")
            self.root.after(0, lambda: messagebox.showerror("Login Error", "Admin ID not found."))

    # --- Database View Operations ---
    def view_rented_items_thread(self):
        if not self.current_admin:
            messagebox.showwarning("Locked", "You must be logged in as an Admin to view database records.")
            return
        threading.Thread(target=self._process_view_rented, daemon=True).start()

    def _process_view_rented(self):
        self.log("\n[WAIT] Fetching currently rented items from database...")
        try:
            res = supabase.table("Inventory").select("name, last_rented_person").eq("is_rented", True).execute()
            rented_items = res.data

            if not rented_items:
                self.log("\n[-] No items are currently rented out.")
            else:
                self.log(f"\n--- Currently Rented Items ({len(rented_items)}) ---")
                for item in rented_items:
                    item_name = item.get("name", "Unknown Item")
                    renter = item.get("last_rented_person", "Unknown Renter")
                    self.log(f" • {item_name}  -->  {renter}")
                self.log("----------------------------------")
        except Exception as e:
            self.log(f"\n[!] Error fetching records: {e}")

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
        if not self.current_admin:
            messagebox.showwarning("Locked", "You must be logged in as an Admin to check out items.")
            return
        if not self.cart:
            messagebox.showwarning("Empty Cart", "The cart is empty! Scan items first.")
            return
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

        current_items.extend(new_item_ids)
        supabase.table("Users").update({"currently_renting": current_items}).eq("id", user['id']).execute()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        admin_name = self.current_admin['name']

        for item in self.cart:
            if item['id'] in new_item_ids:
                history = item.get('rental_history') or []
                history.append(f"{user['name']}/{current_time}/PENDING/Out:{admin_name}")
                
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
        
        choice = gui.ask_yes_no("Return Item", f"Item '{item['name']}' is rented by {renter['name']}.\n\nProcess a Return (Check-in)?")
        if choice:
            condition = gui.ask_string("Item Condition", f"Update condition of '{item['name']}' on return?\n(e.g., Good, Scratched, Damaged):")
            if condition is None: 
                condition = "Not specified"

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            admin_name = gui.current_admin['name']

            history = item.get('rental_history') or []
            if history:
                history[-1] = history[-1].replace("PENDING", f"{current_time}/In:{admin_name}")

            new_list = [i for i in renter['currently_renting'] if i != item['id']]
            supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
            
            update_payload = {
                "is_rented": False,
                "rental_history": history
            }
            if condition != "":
                update_payload["condition"] = condition

            supabase.table("Inventory").update(update_payload).eq("id", item['id']).execute()
            gui.log(f"Item '{item['name']}' returned to Admin {admin_name}. Condition: {condition}.")
            
    else:
        current_condition = item.get('condition', 'Not specified')
        gui.log(f"STATUS: [ AVAILABLE ] (Last Renter: {item.get('last_rented_person', 'None')})")
        gui.log(f"CONDITION: {current_condition}")
        
        choice = gui.ask_yes_no("Add to Cart", f"Item '{item['name']}' is available.\n\nAdd to checkout cart?")
        if choice:
            gui.root.after(0, gui.add_to_cart, item)

def process_tag(tag):
    if not gui.current_admin:
        gui.log("\n[!] System locked. Please log in as an Admin to process items.")
        return

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
        gui.log("\nInventory System Live. Please log in as Admin to scan items.")
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