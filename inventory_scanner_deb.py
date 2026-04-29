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
        
        self.is_authenticated = False
        self.is_authenticating = False # Lock to prevent login thread flooding
        self.current_admin_name = None 
        self.cart = [] 

        # --- Theme Definitions ---
        self.themes = {
            "dark": {
                "bg": "#0f172a",
                "left_bg": "#1e3a8a",
                "right_bg": "#7f1d1d",
                "text": "white",
                "console_bg": "#eff6ff",
                "console_fg": "#0f172a",
                "cart_bg": "#fef2f2",
                "cart_fg": "#7f1d1d",
                "btn_checkout": "#1d4ed8",
                "btn_clear": "#b91c1c",
                "btn_tools": "#475569"
            },
            "light": {
                "bg": "#f8fafc",
                "left_bg": "#bae6fd",
                "right_bg": "#fecaca",
                "text": "#0f172a",
                "console_bg": "#ffffff",
                "console_fg": "#000000",
                "cart_bg": "#ffffff",
                "cart_fg": "#000000",
                "btn_checkout": "#3b82f6",
                "btn_clear": "#ef4444",
                "btn_tools": "#94a3b8"
            }
        }
        self.current_theme = "dark"

        # --- Layout Setup ---
        self.top_frame = tk.Frame(root)
        self.top_frame.pack(side=tk.TOP, fill='x', padx=10, pady=(10, 0))
        
        self.theme_btn = tk.Button(self.top_frame, text="Toggle Theme", command=self.toggle_theme, font=("Consolas", 10, "bold"))
        self.theme_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.view_btn = tk.Button(self.top_frame, text="View All Rented Items", command=self.view_rented_items, font=("Consolas", 10, "bold"))
        self.view_btn.pack(side=tk.LEFT)

        self.left_frame = tk.Frame(root, bd=5)
        self.left_frame.pack(side=tk.LEFT, expand=True, fill='both', padx=(10, 5), pady=10)
        
        self.log_label = tk.Label(self.left_frame, text="System Logs", font=("Consolas", 14, "bold"))
        self.log_label.pack(pady=(5, 5))
        
        self.text_area = scrolledtext.ScrolledText(self.left_frame, wrap=tk.WORD, state='disabled', font=("Consolas", 11))
        self.text_area.pack(expand=True, fill='both', padx=5, pady=5)

        self.right_frame = tk.Frame(root, bd=5, width=450)
        self.right_frame.pack_propagate(False) 
        self.right_frame.pack(side=tk.RIGHT, fill='both', padx=(5, 10), pady=10)
        
        self.cart_label = tk.Label(self.right_frame, text="Rental Cart", font=("Consolas", 18, "bold"))
        self.cart_label.pack(pady=(10, 5))
        
        self.cart_listbox = tk.Listbox(self.right_frame, font=("Consolas", 14), selectbackground="#f87171")
        self.cart_listbox.pack(expand=True, fill='both', padx=10, pady=10) 
        
        self.checkout_btn = tk.Button(self.right_frame, text="Checkout Cart", command=self.checkout_cart_thread, font=("Consolas", 14, "bold"), height=2)
        self.checkout_btn.pack(fill='x', padx=10, pady=(0, 5))

        self.clear_btn = tk.Button(self.right_frame, text="Clear Cart", command=self.clear_cart, font=("Consolas", 14, "bold"), height=2)
        self.clear_btn.pack(fill='x', padx=10, pady=(0, 10))

        # Apply initial theme & show login window
        self.apply_theme()
        self.root.withdraw() 
        self.show_login_window()

    # --- Authentication & Startup Flow ---
    def show_login_window(self):
        self.login_win = tk.Toplevel(self.root)
        self.login_win.title("Admin Login Required")
        self.login_win.geometry("450x250")
        self.login_win.configure(bg="#0f172a")
        self.login_win.resizable(False, False)
        
        tk.Label(self.login_win, text="Admin Authentication Required", font=("Consolas", 14, "bold"), bg="#0f172a", fg="white").pack(pady=(30, 10))
        tk.Label(self.login_win, text="Scan Admin Card or Enter ID Manually:", font=("Consolas", 11), bg="#0f172a", fg="white").pack(pady=5)
        
        self.admin_entry = tk.Entry(self.login_win, font=("Consolas", 12), width=25)
        self.admin_entry.pack(pady=5)
        
        tk.Button(self.login_win, text="Login", command=self.manual_login, bg="#1d4ed8", fg="white", font=("Consolas", 12, "bold")).pack(pady=10)
        self.login_win.protocol("WM_DELETE_WINDOW", self.root.destroy)
        
        self.login_win.transient(self.root)
        self.login_win.grab_set()

    def manual_login(self):
        admin_id = self.admin_entry.get().strip()
        if admin_id:
            if len(admin_id) > 9:
                admin_id = admin_id[1:9]
            self.is_authenticating = True
            threading.Thread(target=self._verify_admin_thread, args=(admin_id,), daemon=True).start()

    def _verify_admin_thread(self, admin_id):
        try:
            res = supabase.table("Admins").select("*").eq("id", admin_id).execute()
            if res.data:
                self.root.after(0, self._login_success, res.data[0])
            else:
                self.root.after(0, self._login_fail)
        except Exception as e:
            self.root.after(0, self._login_error, e)

    def _login_success(self, admin_data):
        self.is_authenticated = True
        self.is_authenticating = False
        self.current_admin_name = admin_data.get('name', admin_data.get('id'))
        self.login_win.destroy()
        self.root.deiconify()
        self.log(f"[!] Authentication Success. Welcome, Admin: {self.current_admin_name}")

    def _login_fail(self):
        self.is_authenticating = False
        messagebox.showerror("Login Failed", "Access Denied: Invalid Admin ID or Card", parent=self.login_win)

    def _login_error(self, e):
        self.is_authenticating = False
        messagebox.showerror("Error", f"Database connection error: {e}", parent=self.login_win)

    # --- Theme Engine ---
    def apply_theme(self):
        t = self.themes[self.current_theme]
        self.root.configure(bg=t["bg"])
        self.top_frame.configure(bg=t["bg"])
        self.left_frame.configure(bg=t["left_bg"])
        self.log_label.configure(bg=t["left_bg"], fg=t["text"])
        self.text_area.configure(bg=t["console_bg"], fg=t["console_fg"])
        self.right_frame.configure(bg=t["right_bg"])
        self.cart_label.configure(bg=t["right_bg"], fg=t["text"])
        self.cart_listbox.configure(bg=t["cart_bg"], fg=t["cart_fg"])
        self.checkout_btn.configure(bg=t["btn_checkout"], fg="white")
        self.clear_btn.configure(bg=t["btn_clear"], fg="white")
        self.theme_btn.configure(bg=t["btn_tools"], fg="white")
        self.view_btn.configure(bg=t["btn_tools"], fg="white")

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme()
        self.log(f"[*] Switched to {self.current_theme} theme.")

    # --- Admin Tools ---
    def view_rented_items(self):
        threading.Thread(target=self._fetch_rented_items_thread, daemon=True).start()

    def _fetch_rented_items_thread(self):
        try:
            res = supabase.table("Inventory").select("*").eq("is_rented", True).execute()
            items = res.data
            
            if not items:
                self.root.after(0, messagebox.showinfo, "Checked Out Items", "No items are currently checked out.")
                return
                
            msg = "Currently Rented Items:\n\n"
            for item in items:
                renter = item.get("last_rented_person", "Unknown")
                msg += f"• {item.get('name', 'Unknown')} (Rented by: {renter})\n"
                
            self.root.after(0, messagebox.showinfo, "Checked Out Items", msg)
        except Exception as e:
            self.root.after(0, messagebox.showerror, "Error", f"Failed to retrieve data: {e}")

    # --- UI Dialog Wrappers ---
    def log(self, msg):
        self.root.after(0, self._log_gui, msg)

    def _log_gui(self, msg):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, str(msg) + "\n")
        self.text_area.see(tk.END)
        self.text_area.configure(state='disabled')

    def ask_string(self, title, prompt):
        local_event = threading.Event()
        result_box = []

        def _ask():
            res = simpledialog.askstring(title, prompt, parent=self.root)
            result_box.append(res)
            local_event.set()

        self.root.after(0, _ask)
        local_event.wait()
        return result_box[0] if result_box else None

    def ask_yes_no(self, title, prompt):
        local_event = threading.Event()
        result_box = []

        def _ask():
            res = messagebox.askyesno(title, prompt, parent=self.root)
            result_box.append(res)
            local_event.set()

        self.root.after(0, _ask)
        local_event.wait()
        return result_box[0] if result_box else False

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
        for item in self.cart:
            if item['id'] in new_item_ids:
                history = item.get('rental_history') or []
                history.append(f"{user['name']}/{current_time}/PENDING (Issued by: {self.current_admin_name})")
                
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
            history = item.get('rental_history') or []
            if history:
                history[-1] = history[-1].replace("PENDING", f"Returned: {current_time} (Received by: {gui.current_admin_name})")

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
        
        choice = gui.ask_yes_no("Add to Cart", f"Item '{item['name']}' is available.\n\nAdd to checkout cart?")
        if choice:
            gui.root.after(0, gui.add_to_cart, item)

def extract_tag_id(tag):
    if tag.ndef and len(tag.ndef.records) > 0:
        for record in tag.ndef.records:
            if isinstance(record, ndef.TextRecord):
                return record.text
    return tag.identifier.hex()

def process_tag(tag, tag_uuid):
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
            clf = nfc.ContactlessFrontend(path)
            if clf:
                gui.log(f"Connected to NFC reader via {path}.")
                break
        except IOError:
            continue
            
    if not clf:
        gui.log("Hardware Error: Could not connect to NFC reader.")
        return

    last_tag_id = None
    last_scan_time = 0

    try:
        while True:
            tag = clf.connect(rdwr={'on-connect': lambda tag: False})
            if tag:
                tag_id = extract_tag_id(tag)
                current_time = time.time()
                
                # DEBOUNCE: Ignore the same tag if scanned within 3 seconds
                if tag_id == last_tag_id and (current_time - last_scan_time) < 3.0:
                    time.sleep(0.5)
                    continue
                
                last_tag_id = tag_id
                last_scan_time = current_time
                
                if not gui.is_authenticated:
                    if not getattr(gui, 'is_authenticating', False):
                        gui.is_authenticating = True
                        threading.Thread(target=gui._verify_admin_thread, args=(tag_id,), daemon=True).start()
                else:
                    process_tag(tag, tag_id)
                    gui.log("\nReady for next tag...")
            time.sleep(0.5)
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