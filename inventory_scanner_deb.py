import os
import uuid
import nfc
import ndef
import time
import threading
import requests
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
discord_webhook_url: str = os.environ.get("DISCORD_WEBHOOK_URL") 
supabase: Client = create_client(url, key)

# --- Thread-Safe GUI Helper ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NFC Arena Inventory System")
        self.root.geometry("1080x850") 
        
        # Base UI Fonts
        self.ui_font = ("Segoe UI", 13, "bold")
        self.header_font = ("Segoe UI", 18, "bold")
        self.log_font = ("Consolas", 12)

        self.cart = [] 
        self.is_dark_mode = True 
        self.current_admin = None 

        # --- Esports/Arena Theme Definitions ---
        self.themes = {
            "dark": {
                "main_bg": "#090C10",          
                "panel_bg": "#161B22",         
                "header_fg": "#58A6FF",        
                "text_bg": "#010409",          
                "text_fg": "#00FF9D",          
                "right_header_fg": "#FF7B72",  
                "list_bg": "#0D1117",          
                "list_fg": "#C9D1D9",          
                "list_sel": "#1F6FEB",         
                "btn_checkout_bg": "#238636",  
                "btn_clear_bg": "#DA3633",     
                "btn_view_bg": "#D29922",      
                "btn_closing_bg": "#8B5CF6",   
                "btn_toggle_bg": "#21262D",    
                "btn_toggle_fg": "#C9D1D9",
                "btn_active_fg": "#FFFFFF",
                "admin_logged_in": "#3FB950",  
                "admin_logged_out": "#F85149"  
            },
            "light": {
                "main_bg": "#F3F4F6",          
                "panel_bg": "#FFFFFF",         
                "header_fg": "#1D4ED8",        
                "text_bg": "#F8FAFC",          
                "text_fg": "#0F172A",          
                "right_header_fg": "#BE123C",  
                "list_bg": "#FFFFFF",          
                "list_fg": "#1E293B",          
                "list_sel": "#93C5FD",         
                "btn_checkout_bg": "#2563EB",  
                "btn_clear_bg": "#E11D48",     
                "btn_view_bg": "#D97706",      
                "btn_closing_bg": "#7C3AED",   
                "btn_toggle_bg": "#E2E8F0",
                "btn_toggle_fg": "#0F172A",
                "btn_active_fg": "#FFFFFF",
                "admin_logged_in": "#059669", 
                "admin_logged_out": "#DC2626" 
            }
        }

        # --- Layout Setup ---
        self.top_header = tk.Label(root, text="⚡ ARENA INVENTORY CTRL ⚡", font=("Segoe UI", 20, "bold"), pady=10)
        self.top_header.pack(fill='x')

        self.left_frame = tk.Frame(root, bd=0, relief="flat")
        self.left_frame.pack(side=tk.LEFT, expand=True, fill='both', padx=(20, 10), pady=(0, 20))
        
        self.log_label = tk.Label(self.left_frame, text="TERMINAL LOGS", font=self.header_font, anchor="w")
        self.log_label.pack(fill='x', pady=(15, 10), padx=5)
        
        self.text_area = scrolledtext.ScrolledText(
            self.left_frame, wrap=tk.WORD, state='disabled', font=self.log_font,
            bd=0, padx=15, pady=15, relief="flat"
        )
        self.text_area.pack(expand=True, fill='both')

        self.right_frame = tk.Frame(root, bd=0, width=400)
        self.right_frame.pack_propagate(False)
        self.right_frame.pack(side=tk.RIGHT, fill='y', padx=(10, 20), pady=(0, 20))
        
        self.toggle_btn = tk.Button(
            self.right_frame, text="☀️ LIGHT SYSTEM", command=self.toggle_theme, 
            font=("Segoe UI", 11, "bold"), bd=0, cursor="hand2", pady=8
        )
        self.toggle_btn.pack(fill='x', pady=(15, 20))

        self.admin_label = tk.Label(self.right_frame, text="ADMIN: OFFLINE", font=self.header_font)
        self.admin_label.pack(pady=(5, 5))

        self.login_btn = tk.Button(
            self.right_frame, text="AUTHENTICATE", command=self.prompt_login_thread, 
            font=self.ui_font, bd=0, cursor="hand2", pady=12
        )
        self.login_btn.pack(fill='x', pady=(0, 25))

        self.cart_label = tk.Label(self.right_frame, text="ACTIVE CART", font=self.header_font)
        self.cart_label.pack(pady=(5, 5))
        
        self.cart_listbox = tk.Listbox(
            self.right_frame, font=self.log_font, bd=0, relief="flat", 
            highlightthickness=0, activestyle="none"
        )
        self.cart_listbox.pack(expand=True, fill='both', pady=(0, 15)) 
        
        self.checkout_btn = tk.Button(
            self.right_frame, text="DEPLOY CART", command=self.checkout_cart_thread, 
            font=self.ui_font, bd=0, cursor="hand2", pady=15
        )
        self.checkout_btn.pack(fill='x', pady=(0, 10))

        self.clear_btn = tk.Button(
            self.right_frame, text="PURGE CART", command=self.clear_cart, 
            font=self.ui_font, bd=0, cursor="hand2", pady=15
        )
        self.clear_btn.pack(fill='x', pady=(0, 10))

        self.view_rented_btn = tk.Button(
            self.right_frame, text="VIEW DEPLOYED ASSETS", command=self.view_rented_items_thread, 
            font=self.ui_font, bd=0, cursor="hand2", pady=15
        )
        self.view_rented_btn.pack(fill='x', pady=(0, 10))

        self.closing_btn = tk.Button(
            self.right_frame, text="NIGHTLOCK PROTOCOL", command=self.closing_protocol_thread, 
            font=self.ui_font, bd=0, cursor="hand2", pady=15
        )
        self.closing_btn.pack(fill='x')

        self.apply_theme()

        self.event = threading.Event()
        self.result = None

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        
        self.root.configure(bg=theme["main_bg"])
        self.top_header.configure(bg=theme["main_bg"], fg=theme["header_fg"])
        
        self.left_frame.configure(bg=theme["panel_bg"])
        self.log_label.configure(bg=theme["panel_bg"], fg=theme["header_fg"])
        self.text_area.configure(bg=theme["text_bg"], fg=theme["text_fg"], insertbackground=theme["text_fg"])
        
        self.right_frame.configure(bg=theme["panel_bg"])
        self.cart_label.configure(bg=theme["panel_bg"], fg=theme["right_header_fg"])
        self.cart_listbox.configure(bg=theme["list_bg"], fg=theme["list_fg"], selectbackground=theme["list_sel"])
        
        def style_btn(btn, bg_color):
            btn.configure(bg=bg_color, fg="white", activebackground=bg_color, activeforeground=theme["btn_active_fg"])

        style_btn(self.checkout_btn, theme["btn_checkout_bg"])
        style_btn(self.clear_btn, theme["btn_clear_bg"])
        style_btn(self.view_rented_btn, theme["btn_view_bg"])
        style_btn(self.closing_btn, theme["btn_closing_bg"]) 
        
        toggle_text = "☀️ LIGHT SYSTEM" if self.is_dark_mode else "🌙 DARK SYSTEM"
        self.toggle_btn.configure(
            text=toggle_text, bg=theme["btn_toggle_bg"], fg=theme["btn_toggle_fg"],
            activebackground=theme["btn_toggle_bg"], activeforeground=theme["btn_toggle_fg"]
        )

        self.admin_label.configure(bg=theme["panel_bg"])
        self._update_admin_ui_colors()

    def _update_admin_ui_colors(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        if self.current_admin:
            self.admin_label.configure(text=f"ADMIN: {self.current_admin['name'].upper()}", fg=theme["admin_logged_in"])
            self.login_btn.configure(text="LOCK TERMINAL", bg=theme["btn_clear_bg"], fg="white", activebackground=theme["btn_clear_bg"])
        else:
            self.admin_label.configure(text="ADMIN: OFFLINE", fg=theme["admin_logged_out"])
            self.login_btn.configure(text="AUTHENTICATE", bg=theme["btn_checkout_bg"], fg="white", activebackground=theme["btn_checkout_bg"])

    def log(self, msg):
        self.root.after(0, self._log_gui, msg)

    def _log_gui(self, msg):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, str(msg) + "\n")
        self.text_area.see(tk.END)
        self.text_area.configure(state='disabled')

    # --- UPDATED: Added initialvalue parameter ---
    def ask_string(self, title, prompt, initialvalue=None):
        self.event.clear()
        self.root.after(0, self._ask_string_gui, title, prompt, initialvalue)
        self.event.wait()
        return self.result

    def _ask_string_gui(self, title, prompt, initialvalue):
        # Now allows passing a pre-filled default value to the input box
        self.result = simpledialog.askstring(title, prompt, initialvalue=initialvalue, parent=self.root)
        self.event.set()

    def ask_yes_no(self, title, prompt):
        self.event.clear()
        self.root.after(0, self._ask_yes_no_gui, title, prompt)
        self.event.wait()
        return self.result

    def _ask_yes_no_gui(self, title, prompt):
        self.result = messagebox.askyesno(title, prompt, parent=self.root)
        self.event.set()

    # --- User Profile Modal GUI ---
    def ask_profile_confirmation(self, user, cart_size):
        self.event.clear()
        self.root.after(0, self._show_profile_modal, user, cart_size)
        self.event.wait()
        return self.result

    def _show_profile_modal(self, user, cart_size):
        modal = tk.Toplevel(self.root)
        modal.title("USER PROFILE REVIEW")
        modal.geometry("450x380")
        modal.transient(self.root) 
        modal.grab_set() 

        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        modal.configure(bg=theme["panel_bg"])

        renting_count = len(user.get('currently_renting') or [])
        strikes = user.get('strike_history') or []
        strike_count = len(strikes)
        strike_color = theme["admin_logged_out"] if strike_count > 0 else theme["admin_logged_in"]

        tk.Label(modal, text="🛡️ PRE-DEPLOYMENT REVIEW 🛡️", font=("Segoe UI", 16, "bold"), bg=theme["panel_bg"], fg=theme["header_fg"]).pack(pady=(20, 15))
        
        tk.Label(modal, text=f"USER ALIAS: {user['name'].upper()}", font=("Segoe UI", 14, "bold"), bg=theme["panel_bg"], fg=theme["list_fg"]).pack(pady=5)
        tk.Label(modal, text=f"CURRENT ASSETS OUT: {renting_count}", font=("Segoe UI", 12), bg=theme["panel_bg"], fg=theme["list_fg"]).pack(pady=5)
        tk.Label(modal, text=f"STRIKES ON RECORD: {strike_count}", font=("Segoe UI", 14, "bold"), bg=theme["panel_bg"], fg=strike_color).pack(pady=5)

        if strike_count > 0:
            latest_strike = strikes[-1]
            if len(latest_strike) > 40:
                latest_strike = latest_strike[:40] + "..."
            tk.Label(modal, text=f"Latest Strike: {latest_strike}", font=("Consolas", 10, "italic"), bg=theme["panel_bg"], fg=theme["admin_logged_out"]).pack(pady=5)

        tk.Label(modal, text=f"Attempting to deploy {cart_size} new asset(s).", font=("Segoe UI", 11, "italic"), bg=theme["panel_bg"], fg=theme["btn_view_bg"]).pack(pady=(15, 10))

        def proceed():
            self.result = True
            modal.destroy()
            self.event.set()

        def cancel():
            self.result = False
            modal.destroy()
            self.event.set()

        btn_frame = tk.Frame(modal, bg=theme["panel_bg"])
        btn_frame.pack(fill="x", pady=20, padx=20)

        tk.Button(btn_frame, text="AUTHORIZE", command=proceed, bg=theme["btn_checkout_bg"], fg="white", font=("Segoe UI", 11, "bold"), cursor="hand2", pady=8).pack(side="left", expand=True, fill="x", padx=5)
        tk.Button(btn_frame, text="DENY & CANCEL", command=cancel, bg=theme["btn_clear_bg"], fg="white", font=("Segoe UI", 11, "bold"), cursor="hand2", pady=8).pack(side="right", expand=True, fill="x", padx=5)
        
        modal.protocol("WM_DELETE_WINDOW", cancel)

    # --- Admin Authentication ---
    def prompt_login_thread(self):
        threading.Thread(target=self._process_login, daemon=True).start()

    def _process_login(self):
        if self.current_admin:
            self.current_admin = None
            self.root.after(0, self._update_admin_ui_colors)
            self.log("\n[-] Admin logged out. Terminal Locked.")
            return

        self.log("\n[WAIT] Awaiting Admin ID scan...")
        a_id = self.ask_string("Authentication", "Scan or enter Admin ID to unlock:")
        
        if not a_id:
            self.log("Authentication cancelled.")
            return

        if len(a_id) > 9:
            a_id = a_id[1:9]

        res = supabase.table("Admins").select("*").eq("id", a_id).execute()
        if res.data:
            self.current_admin = res.data[0]
            self.root.after(0, self._update_admin_ui_colors)
            self.log(f"\n[+] Authorization accepted. Welcome, {self.current_admin['name']}. Terminal Unlocked.")
        else:
            self.log("\n[!] Authorization failed: Invalid Admin ID.")
            self.root.after(0, lambda: messagebox.showerror("Security Error", "Admin ID not recognized."))

    # --- Closing Protocol (Nightlock) ---
    def closing_protocol_thread(self):
        if not self.current_admin:
            messagebox.showwarning("Access Denied", "Terminal locked. Admin credentials required.")
            return
        threading.Thread(target=self._process_closing, daemon=True).start()

    def _process_closing(self):
        self.log("\n[WAIT] Initiating NIGHTLOCK Closing Protocol...")
        confirm = self.ask_yes_no(
            "NIGHTLOCK PROTOCOL", 
            "WARNING: Executing this protocol will issue strikes to ALL users currently holding unreturned assets and dispatch a Discord webhook report.\n\nProceed with Closing Protocol?"
        )
        
        if not confirm:
            self.log("[-] Protocol aborted.")
            return

        try:
            res_items = supabase.table("Inventory").select("id, name, last_rented_person").eq("is_rented", True).execute()
            rented_items = res_items.data

            if not rented_items:
                self.log("[+] Nightlock Complete: 0 assets outstanding. All equipment secured.")
                if discord_webhook_url:
                    requests.post(discord_webhook_url, json={"content": "🛡️ **NIGHTLOCK COMPLETE**: All assets are safely secured in inventory. Goodnight!"})
                return

            res_users = supabase.table("Users").select("*").execute()
            users_with_items = [u for u in res_users.data if u.get('currently_renting')]

            if not users_with_items:
                self.log("[!] Database Anomaly: Items marked rented, but no user profiles hold them.")
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            report_lines = []

            self.log(f"\n>> Issuing automated strikes for {len(rented_items)} missing assets...")

            for user in users_with_items:
                item_ids = user['currently_renting']
                user_items = [item for item in rented_items if item['id'] in item_ids]
                
                if not user_items:
                    continue

                user_strikes = user.get('strike_history') or []
                missing_item_names = []
                
                for item in user_items:
                    missing_item_names.append(item['name'])
                    strike_reason = f"Forgot to return {item['name']}"
                    user_strikes.append(f"[{timestamp}] {strike_reason}")
                
                supabase.table("Users").update({"strike_history": user_strikes}).eq("id", user['id']).execute()
                
                item_list_str = ", ".join(missing_item_names)
                report_lines.append(f"• **{user['name']}** failed to return: *{item_list_str}*")
                self.log(f"[!] Applied {len(user_items)} strike(s) to {user['name']}.")

            if discord_webhook_url:
                webhook_content = "🚨 **NIGHTLOCK PROTOCOL REPORT** 🚨\nThe following users failed to return their equipment before closing and have been automatically issued strikes:\n\n"
                webhook_content += "\n".join(report_lines)
                
                response = requests.post(discord_webhook_url, json={"content": webhook_content})
                
                if response.status_code in [200, 204]:
                    self.log("[SUCCESS] Webhook transmitted to Discord.")
                else:
                    self.log(f"[!] Webhook transmission failed with status {response.status_code}.")
            else:
                self.log("[!] DISCORD_WEBHOOK_URL missing in environment variables. Webhook skipped.")

            self.log("\n=== NIGHTLOCK PROTOCOL FINISHED ===")

        except Exception as e:
            self.log(f"\n[!] Critical error during protocol: {e}")

    # --- Database View Operations ---
    def view_rented_items_thread(self):
        if not self.current_admin:
            messagebox.showwarning("Access Denied", "Terminal locked. Admin credentials required.")
            return
        threading.Thread(target=self._process_view_rented, daemon=True).start()

    def _process_view_rented(self):
        self.log("\n[WAIT] Interrogating database for deployed assets...")
        try:
            res = supabase.table("Inventory").select("name, last_rented_person").eq("is_rented", True).execute()
            rented_items = res.data

            if not rented_items:
                self.log("\n[-] All assets currently secured in inventory.")
            else:
                self.log(f"\n=== DEPLOYED ASSETS ({len(rented_items)}) ===")
                for item in rented_items:
                    item_name = item.get("name", "Unknown Asset")
                    renter = item.get("last_rented_person", "Unknown Renter")
                    self.log(f" >> {item_name.ljust(20)} | {renter}")
                self.log("===============================")
        except Exception as e:
            self.log(f"\n[!] Database Error: {e}")

    # --- Cart Operations ---
    def add_to_cart(self, item):
        if any(cart_item['id'] == item['id'] for cart_item in self.cart):
            self.log(f"[*] {item['name']} already detected in staging.")
            return
        self.cart.append(item)
        self.cart_listbox.insert(tk.END, f"  {item['name']}")
        self.log(f"[+] Staged '{item['name']}' for deployment.")

    def clear_cart(self):
        self.cart.clear()
        self.cart_listbox.delete(0, tk.END)
        self.log("[-] Staging area purged.")

    def checkout_cart_thread(self):
        if not self.current_admin:
            messagebox.showwarning("Access Denied", "Terminal locked. Admin credentials required for deployment.")
            return
        if not self.cart:
            messagebox.showwarning("Empty Staging", "Staging area is empty. Scan assets first.")
            return
        threading.Thread(target=self._process_checkout, daemon=True).start()

    def _process_checkout(self):
        self.log("\n[WAIT] Awaiting User ID for deployment...")
        u_id = self.ask_string("User Scan", f"Deploying {len(self.cart)} assets.\nScan or enter USER CARD ID:")
        
        if not u_id:
            self.log("Deployment cancelled.")
            return

        if len(u_id) > 9:
            u_id = u_id[1:9]

        user = get_user(u_id) or register_user(u_id)
        if not user:
            self.log("Deployment failed: User matrix error.")
            return

        proceed = self.ask_profile_confirmation(user, len(self.cart))
        if not proceed:
            self.log(f"Deployment to {user['name']} denied by Admin.")
            return

        current_items = user.get('currently_renting') or []
        new_item_ids = [item['id'] for item in self.cart if item['id'] not in current_items]
        
        if not new_item_ids:
            self.log("All staged assets already assigned to this user.")
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
        
        self.log(f"\n[SUCCESS] Deployed {len(new_item_ids)} asset(s) to {user['name']}.")
        self.root.after(0, self.clear_cart)


# --- Core Logic ---
def get_user(user_id: str):
    res = supabase.table("Users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None

def get_item(item_uuid: str):
    res = supabase.table("Inventory").select("*").eq("id", item_uuid).execute()
    return res.data[0] if res.data else None

def register_user(user_id: str):
    gui.log(f"\n[!] User ID {user_id} unassigned.")
    name = gui.ask_string("Register User", "Enter alias for new user registration:")
    if name:
        new_user = {"id": user_id, "name": name, "currently_renting": [], "strike_history": []}
        supabase.table("Users").insert(new_user).execute()
        gui.log(f"User '{name}' added to matrix.")
        return new_user
    return None

def handle_existing_item(item):
    gui.log(f"\n--- ASSET DETECTED ---")
    gui.log(f"ID: {item['name']}")
    
    renter_res = supabase.table("Users").select("*").contains("currently_renting", [item['id']]).execute()
    renter = renter_res.data[0] if renter_res.data else None

    if renter:
        gui.log(f"STATUS: [ DEPLOYED ] -> {renter['name']}")
        
        choice = gui.ask_yes_no("Return Asset", f"Asset '{item['name']}' is assigned to {renter['name']}.\n\nProcess Return Check-in?")
        if choice:
            # --- UPDATED: Fetch current condition and pre-fill the dialog box ---
            current_cond = item.get('condition', 'Pristine')
            condition = gui.ask_string(
                "Asset Condition", 
                f"Log condition of '{item['name']}':", 
                initialvalue=current_cond # Injects the current state into the typing box
            )
            if not condition: # If they hit cancel or leave it entirely blank, keep existing
                condition = current_cond

            issue_strike = gui.ask_yes_no("Disciplinary Action", f"Issue a strike to {renter['name']} for the return of this asset?")
            if issue_strike:
                strike_reason = gui.ask_string("Strike Details", "Enter description of the infraction/damage:")
                if strike_reason:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    user_strikes = renter.get('strike_history') or []
                    user_strikes.append(f"[{timestamp}] {strike_reason} (Asset: {item['name']})")
                    supabase.table("Users").update({"strike_history": user_strikes}).eq("id", renter['id']).execute()
                    gui.log(f"[!] Strike recorded on {renter['name']}'s profile.")

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            admin_name = gui.current_admin['name']

            history = item.get('rental_history') or []
            if history:
                history[-1] = history[-1].replace("PENDING", f"{current_time}/In:{admin_name}")

            new_list = [i for i in renter['currently_renting'] if i != item['id']]
            supabase.table("Users").update({"currently_renting": new_list}).eq("id", renter['id']).execute()
            
            update_payload = {
                "is_rented": False,
                "rental_history": history,
                "condition": condition # Save the new (or confirmed existing) condition
            }

            supabase.table("Inventory").update(update_payload).eq("id", item['id']).execute()
            gui.log(f"Asset '{item['name']}' secured by {admin_name}. Condition logged: {condition}.")
            
    else:
        current_condition = item.get('condition', 'Unverified')
        gui.log(f"STATUS: [ SECURED/AVAILABLE ] (Prior Assignment: {item.get('last_rented_person', 'None')})")
        gui.log(f"CONDITION: {current_condition}")
        
        choice = gui.ask_yes_no("Stage Asset", f"Asset '{item['name']}' is available.\n\nStage for deployment?")
        if choice:
            gui.root.after(0, gui.add_to_cart, item)

def process_tag(tag):
    if not gui.current_admin:
        gui.log("\n[!] Terminal locked. Admin authorization required for scans.")
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
            gui.log(f"Unrecognized Hardware Signature: {tag_uuid}")
            if gui.ask_yes_no("New Asset", "Unrecognized Hardware.\nFlash and register as new inventory asset?"):
                flash_new_item(tag, tag_uuid)
    else:
        flash_new_item(tag)

def flash_new_item(tag, existing_uuid=None):
    new_uuid = existing_uuid or str(uuid.uuid4())
    name = gui.ask_string("Register Asset", "Enter designation for NEW asset:")
    if not name: 
        gui.log("Hardware flashing aborted.")
        return

    try:
        if tag.ndef:
            tag.ndef.records = [ndef.TextRecord(new_uuid)]
            supabase.table("Inventory").insert({
                "id": new_uuid, 
                "name": name,
                "condition": "Pristine", 
                "rental_history": []
            }).execute()
            gui.log(f"Hardware flashed. Asset '{name}' synchronized.")
    except Exception as e:
        gui.log(f"Hardware flashing error: {e}")

# --- Background NFC Hardware Loop ---
def nfc_worker():
    clf = None
    connection_paths = ['tty:serial0', 'usb']
    
    for path in connection_paths:
        try:
            gui.log(f"Initializing NFC hardware bridge via {path}...")
            clf = nfc.ContactlessFrontend(path)
            if clf:
                gui.log(f"Hardware bridge established on {path}.")
                break
        except IOError:
            continue
            
    if not clf:
        gui.log("CRITICAL: Hardware bridge failed. Verify NFC reader connection and OS permissions.")
        return

    try:
        gui.log("\n>>> ARENA INVENTORY SYSTEM ONLINE. AWAITING ADMIN AUTH. <<<")
        while True:
            tag = clf.connect(rdwr={'on-connect': lambda tag: False})
            if tag:
                process_tag(tag)
                gui.log("\nScanner ready...")
            time.sleep(1)
    except Exception as e:
        gui.log(f"\nSystem Error / Shutting Down: {e}")
    finally:
        if clf:
            clf.close()

if __name__ == "__main__":
    root = tk.Tk()
    gui = AppGUI(root)
    worker_thread = threading.Thread(target=nfc_worker, daemon=True)
    worker_thread.start()
    root.mainloop()