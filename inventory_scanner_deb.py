import os
import queue
import uuid
import nfc
import ndef
import time
import threading
import requests
import tkinter as tk
import customtkinter as ctk
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")  # must be the service_role key: this kiosk bypasses RLS by design
discord_webhook_url: str = os.environ.get("DISCORD_WEBHOOK_URL")
supabase: Client = create_client(url, key)

# --- Thread-Safe GUI Helper ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LATech Esports Inventory System")
        self.root.geometry("1080x850")

        # Base UI Fonts
        self.ui_font = ctk.CTkFont("Segoe UI", 13, weight="bold")
        self.header_font = ctk.CTkFont("Segoe UI", 18, weight="bold")
        self.log_font = ctk.CTkFont("Consolas", 12)

        self.cart = []
        self.is_dark_mode = True
        self.current_admin = None
        self._cart_rows = []

        # --- Esports Theme Definitions ---
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
        self.top_header = ctk.CTkLabel(root, text="⚡ LATECH ESPORTS INVENTORY CTRL ⚡", font=ctk.CTkFont("Segoe UI", 20, weight="bold"), corner_radius=0)
        self.top_header.pack(fill='x', pady=10)

        self.left_frame = ctk.CTkFrame(root, corner_radius=12, border_width=0)
        self.left_frame.pack(side=tk.LEFT, expand=True, fill='both', padx=(20, 10), pady=(0, 20))

        self.log_label = ctk.CTkLabel(self.left_frame, text="TERMINAL LOGS", font=self.header_font, anchor="w")
        self.log_label.pack(fill='x', pady=(15, 10), padx=15)

        self.text_area = ctk.CTkTextbox(
            self.left_frame, wrap=tk.WORD, state='disabled', font=self.log_font,
            corner_radius=8, border_width=0
        )
        self.text_area.pack(expand=True, fill='both', padx=15, pady=(0, 15))

        self.right_frame = ctk.CTkFrame(root, corner_radius=12, border_width=0, width=400)
        self.right_frame.pack_propagate(False)
        self.right_frame.pack(side=tk.RIGHT, fill='y', padx=(10, 20), pady=(0, 20))

        self.toggle_btn = ctk.CTkButton(
            self.right_frame, text="☀️ LIGHT SYSTEM", command=self.toggle_theme,
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"), corner_radius=8, cursor="hand2", height=36
        )
        self.toggle_btn.pack(fill='x', padx=15, pady=(15, 20))

        self.admin_label = ctk.CTkLabel(self.right_frame, text="ADMIN: OFFLINE", font=self.header_font)
        self.admin_label.pack(pady=(5, 5))

        self.login_btn = ctk.CTkButton(
            self.right_frame, text="AUTHENTICATE", command=self.prompt_login_thread,
            font=self.ui_font, corner_radius=8, cursor="hand2", height=44
        )
        self.login_btn.pack(fill='x', padx=15, pady=(0, 25))

        self.cart_label = ctk.CTkLabel(self.right_frame, text="ACTIVE CART", font=self.header_font)
        self.cart_label.pack(pady=(5, 5))

        self.cart_listbox = ctk.CTkScrollableFrame(
            self.right_frame, corner_radius=8, border_width=0
        )
        self.cart_listbox.pack(expand=True, fill='both', padx=15, pady=(0, 15))

        self.checkout_btn = ctk.CTkButton(
            self.right_frame, text="DEPLOY CART", command=self.checkout_cart_thread,
            font=self.ui_font, corner_radius=8, cursor="hand2", height=48
        )
        self.checkout_btn.pack(fill='x', padx=15, pady=(0, 10))

        self.clear_btn = ctk.CTkButton(
            self.right_frame, text="PURGE CART", command=self.clear_cart,
            font=self.ui_font, corner_radius=8, cursor="hand2", height=48
        )
        self.clear_btn.pack(fill='x', padx=15, pady=(0, 10))

        self.view_rented_btn = ctk.CTkButton(
            self.right_frame, text="VIEW DEPLOYED ASSETS", command=self.view_rented_items_thread,
            font=self.ui_font, corner_radius=8, cursor="hand2", height=48
        )
        self.view_rented_btn.pack(fill='x', padx=15, pady=(0, 10))

        self.closing_btn = ctk.CTkButton(
            self.right_frame, text="NIGHTLOCK PROTOCOL", command=self.closing_protocol_thread,
            font=self.ui_font, corner_radius=8, cursor="hand2", height=48
        )
        self.closing_btn.pack(fill='x', padx=15, pady=(0, 15))

        self.apply_theme()

        self.event = threading.Event()
        self.result = None

        # Tk 9.0 on macOS does not reliably wake the run loop when .after() is
        # scheduled from a non-main thread -- the call silently no-ops. Worker
        # threads hand off to the GUI exclusively through this queue, which is
        # only ever drained by a poll loop scheduled from the main thread.
        self._ui_queue = queue.Queue()
        self.root.after(50, self._drain_ui_queue)

    def dispatch(self, fn, *args):
        self._ui_queue.put((fn, args))

    def _drain_ui_queue(self):
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        ctk.set_appearance_mode("dark" if self.is_dark_mode else "light")

        self.root.configure(fg_color=theme["main_bg"])
        self.top_header.configure(fg_color=theme["main_bg"], text_color=theme["header_fg"])

        self.left_frame.configure(fg_color=theme["panel_bg"])
        self.log_label.configure(fg_color="transparent", text_color=theme["header_fg"])
        self.text_area.configure(fg_color=theme["text_bg"], text_color=theme["text_fg"])

        self.right_frame.configure(fg_color=theme["panel_bg"])
        self.cart_label.configure(fg_color="transparent", text_color=theme["right_header_fg"])
        self.cart_listbox.configure(fg_color=theme["list_bg"])
        for row in self._cart_rows:
            row.configure(fg_color=theme["list_bg"], text_color=theme["list_fg"])

        def style_btn(btn, bg_color):
            btn.configure(fg_color=bg_color, text_color="white", hover_color=bg_color)

        style_btn(self.checkout_btn, theme["btn_checkout_bg"])
        style_btn(self.clear_btn, theme["btn_clear_bg"])
        style_btn(self.view_rented_btn, theme["btn_view_bg"])
        style_btn(self.closing_btn, theme["btn_closing_bg"])

        toggle_text = "☀️ LIGHT SYSTEM" if self.is_dark_mode else "🌙 DARK SYSTEM"
        self.toggle_btn.configure(
            text=toggle_text, fg_color=theme["btn_toggle_bg"], text_color=theme["btn_toggle_fg"],
            hover_color=theme["btn_toggle_bg"]
        )

        self.admin_label.configure(fg_color="transparent")
        self._update_admin_ui_colors()

    def _update_admin_ui_colors(self):
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        if self.current_admin:
            self.admin_label.configure(text=f"ADMIN: {self.current_admin['name'].upper()}", text_color=theme["admin_logged_in"])
            self.login_btn.configure(text="LOCK TERMINAL", fg_color=theme["btn_clear_bg"], text_color="white", hover_color=theme["btn_clear_bg"])
        else:
            self.admin_label.configure(text="ADMIN: OFFLINE", text_color=theme["admin_logged_out"])
            self.login_btn.configure(text="AUTHENTICATE", fg_color=theme["btn_checkout_bg"], text_color="white", hover_color=theme["btn_checkout_bg"])

    def log(self, msg):
        self.dispatch(self._log_gui, msg)

    def _log_gui(self, msg):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, str(msg) + "\n")
        self.text_area.see(tk.END)
        self.text_area.configure(state='disabled')

    def center_window(self, win, width, height):
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

    # --- CUSTOM MODAL REPLACEMENTS ---
    def ask_string(self, title, prompt):
        self.event.clear()
        self.dispatch(self._custom_ask_string_gui, title, prompt)
        self.event.wait()
        return self.result

    def _custom_ask_string_gui(self, title, prompt):
        modal = ctk.CTkToplevel(self.root)
        modal.title(title)
        self.center_window(modal, 450, 220)
        modal.transient(self.root)
        modal.grab_set()
        modal.lift()
        modal.attributes("-topmost", True)
        modal.after_idle(lambda: modal.attributes("-topmost", False))
        modal.focus_force()

        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        modal.configure(fg_color=theme["panel_bg"])

        ctk.CTkLabel(modal, text=prompt, font=ctk.CTkFont("Segoe UI", 12), text_color=theme["list_fg"], wraplength=400, justify="center").pack(pady=(20, 15))

        entry = ctk.CTkEntry(modal, font=ctk.CTkFont("Segoe UI", 14), fg_color=theme["text_bg"], text_color=theme["text_fg"], border_color=theme["btn_toggle_bg"], border_width=1, corner_radius=6)
        entry.pack(fill="x", padx=40, pady=(0, 20))
        entry.focus_set()

        def submit(event=None):
            val = entry.get().strip()
            self.result = val if val else None
            modal.destroy()
            self.event.set()

        def cancel():
            self.result = None
            modal.destroy()
            self.event.set()

        modal.bind('<Return>', submit)
        modal.protocol("WM_DELETE_WINDOW", cancel)

        btn_frame = ctk.CTkFrame(modal, fg_color=theme["panel_bg"])
        btn_frame.pack(fill="x", padx=40)
        ctk.CTkButton(btn_frame, text="SUBMIT", command=submit, fg_color=theme["btn_checkout_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=36).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="CANCEL", command=cancel, fg_color=theme["btn_toggle_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=36).pack(side="right", expand=True, fill="x", padx=(5, 0))

    def ask_yes_no(self, title, prompt):
        self.event.clear()
        self.dispatch(self._custom_ask_yes_no_gui, title, prompt)
        self.event.wait()
        return self.result

    def _custom_ask_yes_no_gui(self, title, prompt):
        modal = ctk.CTkToplevel(self.root)
        modal.title(title)
        self.center_window(modal, 450, 220)
        modal.transient(self.root)
        modal.grab_set()
        modal.lift()
        modal.attributes("-topmost", True)
        modal.after_idle(lambda: modal.attributes("-topmost", False))
        modal.focus_force()

        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        modal.configure(fg_color=theme["panel_bg"])

        ctk.CTkLabel(modal, text=prompt, font=ctk.CTkFont("Segoe UI", 12), text_color=theme["list_fg"], wraplength=400, justify="center").pack(pady=(30, 25), expand=True)

        def yes():
            self.result = True
            modal.destroy()
            self.event.set()

        def no():
            self.result = False
            modal.destroy()
            self.event.set()

        modal.protocol("WM_DELETE_WINDOW", no)

        btn_frame = ctk.CTkFrame(modal, fg_color=theme["panel_bg"])
        btn_frame.pack(fill="x", padx=40, pady=(0, 20))
        ctk.CTkButton(btn_frame, text="YES / PROCEED", command=yes, fg_color=theme["btn_checkout_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=40).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="NO / ABORT", command=no, fg_color=theme["btn_clear_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=40).pack(side="right", expand=True, fill="x", padx=(5, 0))

    # --- Unified Return & Strike Menu ---
    def ask_return_asset(self, item_name, renter_name, previous_condition):
        self.event.clear()
        self.dispatch(self._show_return_modal, item_name, renter_name, previous_condition)
        self.event.wait()
        return self.result

    def _show_return_modal(self, item_name, renter_name, previous_condition):
        modal = ctk.CTkToplevel(self.root)
        modal.title("ASSET RETURN")
        self.center_window(modal, 500, 420)
        modal.transient(self.root)
        modal.grab_set()
        modal.lift()
        modal.attributes("-topmost", True)
        modal.after_idle(lambda: modal.attributes("-topmost", False))
        modal.focus_force()

        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        modal.configure(fg_color=theme["panel_bg"])

        ctk.CTkLabel(modal, text="📥 ASSET RETURN CHECK-IN", font=ctk.CTkFont("Segoe UI", 16, weight="bold"), text_color=theme["header_fg"]).pack(pady=(20, 10))
        ctk.CTkLabel(modal, text=f"Asset: {item_name}", font=ctk.CTkFont("Segoe UI", 12), text_color=theme["list_fg"]).pack()
        ctk.CTkLabel(modal, text=f"Assigned To: {renter_name}", font=ctk.CTkFont("Segoe UI", 12), text_color=theme["list_fg"]).pack(pady=(0, 15))

        # Condition Input
        ctk.CTkLabel(modal, text="Asset Condition:", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), text_color=theme["list_fg"]).pack()
        cond_entry = ctk.CTkEntry(modal, font=ctk.CTkFont("Segoe UI", 12), fg_color=theme["text_bg"], text_color=theme["text_fg"], border_color=theme["btn_toggle_bg"], border_width=1, corner_radius=6)

        cond_entry.insert(0, previous_condition or "Pristine")

        cond_entry.pack(fill="x", padx=50, pady=(0, 20))

        # Strike Input
        ctk.CTkLabel(modal, text="Disciplinary Strike (Leave blank if none):", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), text_color=theme["admin_logged_out"]).pack()
        strike_entry = ctk.CTkEntry(modal, font=ctk.CTkFont("Segoe UI", 12), fg_color=theme["text_bg"], text_color=theme["text_fg"], border_color=theme["admin_logged_out"], border_width=1, corner_radius=6)
        strike_entry.pack(fill="x", padx=50, pady=(0, 25))

        def confirm():
            self.result = {
                "proceed": True,
                "condition": cond_entry.get().strip() or "Unverified",
                "strike_reason": strike_entry.get().strip()
            }
            modal.destroy()
            self.event.set()

        def cancel():
            self.result = {"proceed": False}
            modal.destroy()
            self.event.set()

        modal.protocol("WM_DELETE_WINDOW", cancel)

        btn_frame = ctk.CTkFrame(modal, fg_color=theme["panel_bg"])
        btn_frame.pack(fill="x", padx=40, pady=(0, 20))
        ctk.CTkButton(btn_frame, text="SECURE ASSET", command=confirm, fg_color=theme["btn_checkout_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=44).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="CANCEL", command=cancel, fg_color=theme["btn_toggle_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=44).pack(side="right", expand=True, fill="x", padx=(5, 0))

    # --- Profile Confirmation Modal ---
    def ask_profile_confirmation(self, name, renting_count, strikes, cart_size):
        self.event.clear()
        self.dispatch(self._show_profile_modal, name, renting_count, strikes, cart_size)
        self.event.wait()
        return self.result

    def _show_profile_modal(self, name, renting_count, strikes, cart_size):
        modal = ctk.CTkToplevel(self.root)
        modal.title("USER PROFILE REVIEW")
        self.center_window(modal, 450, 380)
        modal.transient(self.root)
        modal.grab_set()
        modal.lift()
        modal.attributes("-topmost", True)
        modal.after_idle(lambda: modal.attributes("-topmost", False))
        modal.focus_force()

        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        modal.configure(fg_color=theme["panel_bg"])

        strike_count = len(strikes)
        strike_color = theme["admin_logged_out"] if strike_count > 0 else theme["admin_logged_in"]

        ctk.CTkLabel(modal, text="🛡️ PRE-DEPLOYMENT REVIEW 🛡️", font=ctk.CTkFont("Segoe UI", 16, weight="bold"), text_color=theme["header_fg"]).pack(pady=(20, 15))
        ctk.CTkLabel(modal, text=f"USER ALIAS: {name.upper()}", font=ctk.CTkFont("Segoe UI", 14, weight="bold"), text_color=theme["list_fg"]).pack(pady=5)
        ctk.CTkLabel(modal, text=f"CURRENT ASSETS OUT: {renting_count}", font=ctk.CTkFont("Segoe UI", 12), text_color=theme["list_fg"]).pack(pady=5)
        ctk.CTkLabel(modal, text=f"STRIKES ON RECORD: {strike_count}", font=ctk.CTkFont("Segoe UI", 14, weight="bold"), text_color=strike_color).pack(pady=5)

        if strike_count > 0:
            latest_strike = strikes[-1]
            if len(latest_strike) > 40:
                latest_strike = latest_strike[:40] + "..."
            ctk.CTkLabel(modal, text=f"Latest Strike: {latest_strike}", font=ctk.CTkFont("Consolas", 10, slant="italic"), text_color=theme["admin_logged_out"]).pack(pady=5)

        ctk.CTkLabel(modal, text=f"Attempting to deploy {cart_size} new asset(s).", font=ctk.CTkFont("Segoe UI", 11, slant="italic"), text_color=theme["btn_view_bg"]).pack(pady=(15, 10))

        def proceed():
            self.result = True
            modal.destroy()
            self.event.set()

        def cancel():
            self.result = False
            modal.destroy()
            self.event.set()

        modal.protocol("WM_DELETE_WINDOW", cancel)

        btn_frame = ctk.CTkFrame(modal, fg_color=theme["panel_bg"])
        btn_frame.pack(fill="x", pady=20, padx=20)
        ctk.CTkButton(btn_frame, text="AUTHORIZE", command=proceed, fg_color=theme["btn_checkout_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=40).pack(side="left", expand=True, fill="x", padx=5)
        ctk.CTkButton(btn_frame, text="DENY", command=cancel, fg_color=theme["btn_clear_bg"], text_color="white", font=ctk.CTkFont("Segoe UI", 11, weight="bold"), cursor="hand2", corner_radius=6, height=40).pack(side="right", expand=True, fill="x", padx=5)

    # --- Admin Authentication ---
    def prompt_login_thread(self):
        threading.Thread(target=self._process_login, daemon=True).start()

    def _process_login(self):
        if self.current_admin:
            self.current_admin = None
            self.dispatch(self._update_admin_ui_colors)
            self.log("\n[-] Admin logged out. Terminal Locked.")
            return

        self.log("\n[WAIT] Awaiting Admin ID scan...")
        a_id = self.ask_string("Authentication", "Scan or enter Admin ID to unlock terminal:")

        if not a_id:
            self.log("Authentication cancelled.")
            return

        if len(a_id) > 9:
            a_id = a_id[1:9]

        profile = get_profile_by_card(a_id)
        if profile and profile.get("is_admin"):
            self.current_admin = {"id": profile["id"], "name": profile.get("full_name") or "Admin"}
            self.dispatch(self._update_admin_ui_colors)
            self.log(f"\n[+] Authorization accepted. Welcome, {self.current_admin['name']}. Terminal Unlocked.")
        else:
            self.log("\n[!] Authorization failed: Invalid or non-admin card.")
            self.ask_yes_no("Security Alert", "Admin card not recognized. Authorization Denied.")

    # --- Closing Protocol (Nightlock) ---
    def closing_protocol_thread(self):
        threading.Thread(target=self._process_closing, daemon=True).start()

    def _process_closing(self):
        if not self.current_admin:
            self.ask_yes_no("Access Denied", "Terminal locked. Admin credentials required to initiate Closing Protocol.")
            return

        self.log("\n[WAIT] Initiating NIGHTLOCK Closing Protocol...")
        confirm = self.ask_yes_no(
            "NIGHTLOCK PROTOCOL",
            "WARNING: Executing this protocol will issue strikes to ALL users currently holding unreturned assets and dispatch a Discord webhook report.\n\nProceed with Closing Protocol?"
        )

        if not confirm:
            self.log("[-] Protocol aborted.")
            return

        try:
            res = (
                supabase.table("inventory_checkouts")
                .select("id, item_id, user_id, inventory_items(name), profiles!user_id(full_name)")
                .is_("checked_in_at", "null")
                .execute()
            )
            open_checkouts = res.data

            if not open_checkouts:
                self.log("[+] Nightlock Complete: 0 assets outstanding. All equipment secured.")
                if discord_webhook_url:
                    requests.post(discord_webhook_url, json={"content": "🛡️ **NIGHTLOCK COMPLETE**: All LATech Esports assets are safely secured. Goodnight!"})
                return

            by_user = {}
            for co in open_checkouts:
                uid = co["user_id"]
                uname = (co.get("profiles") or {}).get("full_name") or "Unknown User"
                iname = (co.get("inventory_items") or {}).get("name") or "Unknown Asset"
                bucket = by_user.setdefault(uid, {"name": uname, "items": []})
                bucket["items"].append((co["item_id"], iname))

            self.log(f"\n>> Issuing automated strikes for {len(open_checkouts)} missing assets...")

            report_lines = []
            strike_rows = []
            for uid, info in by_user.items():
                item_names = [name for _, name in info["items"]]
                for item_id, iname in info["items"]:
                    strike_rows.append({
                        "user_id": uid,
                        "item_id": item_id,
                        "reason": f"Forgot to return {iname}",
                    })
                report_lines.append(f"• **{info['name']}** failed to return: *{', '.join(item_names)}*")
                self.log(f"[!] Applied {len(info['items'])} strike(s) to {info['name']}.")

            supabase.table("inventory_strikes").insert(strike_rows).execute()

            if discord_webhook_url:
                webhook_content = "🚨 **LATECH ESPORTS NIGHTLOCK REPORT** 🚨\nThe following users failed to return their equipment before closing and have been automatically issued strikes:\n\n"
                webhook_content += "\n".join(report_lines)

                response = requests.post(discord_webhook_url, json={"content": webhook_content})
                if response.status_code in [200, 204]:
                    self.log("[SUCCESS] Webhook transmitted to Discord.")
                else:
                    self.log(f"[!] Webhook transmission failed with status {response.status_code}.")

            self.log("\n=== NIGHTLOCK PROTOCOL FINISHED ===")

        except Exception as e:
            self.log(f"\n[!] Critical error during protocol: {e}")

    # --- Database View Operations ---
    def view_rented_items_thread(self):
        threading.Thread(target=self._process_view_rented, daemon=True).start()

    def _process_view_rented(self):
        if not self.current_admin:
            self.ask_yes_no("Access Denied", "Terminal locked. Admin credentials required.")
            return

        self.log("\n[WAIT] Interrogating database for deployed assets...")
        try:
            res = (
                supabase.table("inventory_checkouts")
                .select("inventory_items(name), profiles!user_id(full_name)")
                .is_("checked_in_at", "null")
                .execute()
            )
            rows = res.data

            if not rows:
                self.log("\n[-] All assets currently secured in inventory.")
            else:
                self.log(f"\n=== DEPLOYED ASSETS ({len(rows)}) ===")
                for row in rows:
                    item_name = (row.get("inventory_items") or {}).get("name") or "Unknown Asset"
                    renter = (row.get("profiles") or {}).get("full_name") or "Unknown Renter"
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
        theme = self.themes["dark"] if self.is_dark_mode else self.themes["light"]
        row = ctk.CTkLabel(
            self.cart_listbox, text=f"  {item['name']}", font=self.log_font, anchor="w",
            fg_color=theme["list_bg"], text_color=theme["list_fg"]
        )
        row.pack(fill="x", pady=2)
        self._cart_rows.append(row)
        self.log(f"[+] Staged '{item['name']}' for deployment.")

    def clear_cart(self):
        self.cart.clear()
        for row in self._cart_rows:
            row.destroy()
        self._cart_rows.clear()
        self.log("[-] Staging area purged.")

    def checkout_cart_thread(self):
        threading.Thread(target=self._process_checkout, daemon=True).start()

    def _process_checkout(self):
        if not self.current_admin:
            self.ask_yes_no("Access Denied", "Terminal locked. Admin credentials required for deployment.")
            return
        if not self.cart:
            self.ask_yes_no("Empty Staging", "Staging area is empty. Scan assets first.")
            return

        self.log("\n[WAIT] Awaiting User ID for deployment...")
        u_id = self.ask_string("User Scan", f"Deploying {len(self.cart)} assets.\nScan or enter USER CARD ID:")

        if not u_id:
            self.log("Deployment cancelled.")
            return

        if len(u_id) > 9:
            u_id = u_id[1:9]

        profile = get_or_register_user_by_card(u_id)
        if not profile:
            self.log("Deployment failed: User matrix error.")
            return

        renting_count = count_open_checkouts(profile["id"])
        strikes = get_strike_history(profile["id"])
        proceed = self.ask_profile_confirmation(profile["full_name"], renting_count, strikes, len(self.cart))
        if not proceed:
            self.log(f"Deployment to {profile['full_name']} denied by Admin.")
            return

        admin_id = self.current_admin["id"]
        current_time = datetime.now(timezone.utc).isoformat()
        checked_out_count = 0

        for item in self.cart:
            if get_open_checkout(item["id"]):
                self.log(f"'{item['name']}' is already checked out; skipping.")
                continue

            supabase.table("inventory_checkouts").insert({
                "item_id": item["id"],
                "user_id": profile["id"],
                "checked_out_at": current_time,
                "checked_out_by": admin_id,
            }).execute()

            supabase.table("inventory_items").update({
                "is_rented": True,
                "last_rented_person": profile["id"],
            }).eq("id", item["id"]).execute()

            checked_out_count += 1

        if checked_out_count:
            self.log(f"\n[SUCCESS] Deployed {checked_out_count} asset(s) to {profile['full_name']}.")
        else:
            self.log("All staged assets already assigned to this user.")

        self.dispatch(self.clear_cart)


# --- Core Logic ---
def get_profile(profile_id: str):
    res = supabase.table("profiles").select("*").eq("id", profile_id).execute()
    return res.data[0] if res.data else None

def get_profile_by_card(card_id: str):
    res = (
        supabase.table("inventory_card_links")
        .select("profile_id, profiles(*)")
        .eq("card_id", card_id)
        .execute()
    )
    return res.data[0]["profiles"] if res.data else None

def link_card_to_profile(card_id: str, profile_id: str):
    supabase.table("inventory_card_links").upsert(
        {"card_id": card_id, "profile_id": profile_id}, on_conflict="card_id"
    ).execute()

def create_shadow_profile(name: str):
    # Kiosk-provisioned account: no real login is ever expected, it only exists
    # to satisfy the profiles -> auth.users foreign key for card-based lookups.
    shadow_email = f"kiosk-{uuid.uuid4().hex}@inventory.local"
    auth_res = supabase.auth.admin.create_user({
        "email": shadow_email,
        "password": uuid.uuid4().hex,
        "email_confirm": True,
        "user_metadata": {"full_name": name, "provisioned_via": "inventory_kiosk"},
    })
    new_id = auth_res.user.id
    supabase.table("profiles").upsert(
        {"id": new_id, "full_name": name, "is_admin": False}, on_conflict="id"
    ).execute()
    return get_profile(new_id)

def get_or_register_user_by_card(card_id: str):
    profile = get_profile_by_card(card_id)
    if profile:
        return profile

    gui.log(f"\n[!] Card {card_id} unassigned.")
    name = gui.ask_string("Register User", "Enter alias for new LATech Esports user registration:")
    if not name:
        return None

    profile = create_shadow_profile(name)
    link_card_to_profile(card_id, profile["id"])
    gui.log(f"User '{name}' added to matrix.")
    return profile

def get_item(item_uuid: str):
    res = supabase.table("inventory_items").select("*").eq("id", item_uuid).execute()
    return res.data[0] if res.data else None

def get_open_checkout(item_id: str):
    res = (
        supabase.table("inventory_checkouts")
        .select("*")
        .eq("item_id", item_id)
        .is_("checked_in_at", "null")
        .order("checked_out_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None

def get_strike_history(profile_id: str):
    res = (
        supabase.table("inventory_strikes")
        .select("reason, issued_at")
        .eq("user_id", profile_id)
        .order("issued_at")
        .execute()
    )
    return [f"[{s['issued_at']}] {s['reason']}" for s in res.data]

def count_open_checkouts(profile_id: str):
    res = (
        supabase.table("inventory_checkouts")
        .select("id", count="exact")
        .eq("user_id", profile_id)
        .is_("checked_in_at", "null")
        .execute()
    )
    return res.count or 0

def handle_existing_item(item):
    gui.log(f"\n--- ASSET DETECTED ---")
    gui.log(f"ID: {item['name']}")

    checkout = get_open_checkout(item["id"])

    if checkout:
        renter = get_profile(checkout["user_id"])
        renter_name = renter["full_name"] if renter else "Unknown"
        gui.log(f"STATUS: [ DEPLOYED ] -> {renter_name}")

        return_data = gui.ask_return_asset(item["name"], renter_name, item.get("condition"))

        if return_data and return_data.get("proceed"):
            condition = return_data.get("condition")
            strike_reason = return_data.get("strike_reason")
            admin_id = gui.current_admin["id"]
            admin_name = gui.current_admin["name"]

            if strike_reason and renter:
                supabase.table("inventory_strikes").insert({
                    "user_id": renter["id"],
                    "item_id": item["id"],
                    "reason": strike_reason,
                    "issued_by": admin_id,
                }).execute()
                gui.log(f"[!] Strike recorded on {renter_name}'s profile.")

                if discord_webhook_url:
                    webhook_content = f"⚠️ **STRIKE ISSUED** ⚠️\n**User:** {renter_name}\n**Asset:** {item['name']}\n**Reason:** {strike_reason}\n**Issued By:** {admin_name}"
                    requests.post(discord_webhook_url, json={"content": webhook_content})

            supabase.table("inventory_checkouts").update({
                "checked_in_at": datetime.now(timezone.utc).isoformat(),
                "checked_in_by": admin_id,
                "condition_at_return": condition,
            }).eq("id", checkout["id"]).execute()

            supabase.table("inventory_items").update({
                "is_rented": False,
                "condition": condition,
            }).eq("id", item["id"]).execute()

            gui.log(f"Asset '{item['name']}' secured by {admin_name}. Condition logged: {condition}.")

    else:
        current_condition = item.get('condition') or 'Unverified'
        gui.log(f"STATUS: [ SECURED/AVAILABLE ]")
        gui.log(f"CONDITION: {current_condition}")

        choice = gui.ask_yes_no("Stage Asset", f"Asset '{item['name']}' is available.\n\nStage for deployment?")
        if choice:
            gui.dispatch(gui.add_to_cart, item)

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
            supabase.table("inventory_items").insert({
                "id": new_uuid,
                "name": name,
                "condition": "Pristine",
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
        gui.log("\n>>> LATECH ESPORTS INVENTORY SYSTEM ONLINE. AWAITING ADMIN AUTH. <<<")
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
    root = ctk.CTk()
    gui = AppGUI(root)
    worker_thread = threading.Thread(target=nfc_worker, daemon=True)
    worker_thread.start()
    root.mainloop()
