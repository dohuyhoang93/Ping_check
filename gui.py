import socket
import threading
import json
import tkinter as tk
from tkinter import LEFT, RIGHT, X, BOTH, YES, NORMAL, DISABLED, TOP, BOTTOM
from tkinter import ttk
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox, simpledialog
import os
import sys
import subprocess
import platform
import time
from collections import deque
import queue
from datetime import datetime

BACKEND_HOST = '127.0.0.1'
BACKEND_PORT = 7878

class PingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Multi-IP Ping Monitor')
        self.root.geometry('1000x700')
        self.root.minsize(800, 600)
        
        # Set icon for the GUI window
        if platform.system() == "Windows":
            icon_path = os.path.join(os.path.dirname(sys.executable), "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        
        self.style = Style('superhero')
        self.current_theme = 'superhero'
        
        self.sock = None
        self.recv_thread = None
        self.running = False
        self.ip_stats = {}
        self.interval = 1000
        self.backend_process = None
        
        self.update_queue = queue.Queue()
        self.last_table_update = 0
        self.update_interval = 1000
        self.stats_buffer = {}
        self.update_pending = False
        
        self.message_count = 0
        self.last_message_time = time.time()
        
        self.selected_ips = {}
        self.connection_indicator = None  # Khởi tạo trước để tránh lỗi
        
        try:
            self._build_ui()
        except Exception as e:
            print(f"UI build failed: {e}")
            self.root.destroy()
            sys.exit(1)
        
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        
        try:
            self.start_backend()
        except Exception as e:
            print(f"Backend start failed: {e}")
            self.root.destroy()
            sys.exit(1)
        
        self._start_update_scheduler()

    def start_backend(self):
        try:
            backend_name = "ping_check.exe" if platform.system() == "Windows" else "ping_check"
            possible_paths = [
                os.path.join(os.path.dirname(sys.executable), backend_name),
                os.path.join(os.path.dirname(__file__), backend_name),
                os.path.join(os.path.dirname(__file__), "target", "release", backend_name)
            ]
            backend_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    backend_path = path
                    break
            if not backend_path:
                messagebox.showerror("Error", f"Backend binary '{backend_name}' not found in: {possible_paths}")
                self.root.destroy()
                sys.exit(1)
            
            print(f"Starting backend: {backend_path}")
            if self.backend_process and self.backend_process.poll() is None:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=2)
            # Giữ nguyên cách chạy như khi thủ công
            self.backend_process = subprocess.Popen(
                [backend_path],
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                start_new_session=True
            )
            time.sleep(1)
            if self.backend_process.poll() is not None:
                stderr = self.backend_process.stderr.read().decode()
                messagebox.showerror("Error", f"Backend process failed: {stderr}")
                self.root.destroy()
                sys.exit(1)
            self.connect_backend()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start backend: {str(e)}")
            self.root.destroy()
            sys.exit(1)

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=YES)

        self._create_header(main_frame)
        self._create_control_panel(main_frame)
        self._create_table(main_frame)
        self._create_status_bar(main_frame)

        self.ip_list = []

    def _create_header(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=X, pady=(0, 15))
        
        title_label = ttk.Label(
            header_frame, 
            text="Multi-IP Ping Monitor", 
            font=('Segoe UI', 18, 'bold')
        )
        title_label.pack(side=LEFT)
        
        self.connection_frame = ttk.Frame(header_frame)
        self.connection_frame.pack(side=RIGHT)
        
        self.connection_indicator = ttk.Label(
            self.connection_frame,
            text="●",
            foreground="red",
            font=('Segoe UI', 16)
        )
        self.connection_indicator.pack(side=LEFT, padx=(0, 5))
        
        self.connection_label = ttk.Label(
            self.connection_frame,
            text="Disconnected",
            font=('Segoe UI', 10)
        )
        self.connection_label.pack(side=LEFT)
        
        self.perf_label = ttk.Label(
            self.connection_frame,
            text="",
            font=('Segoe UI', 8)
        )
        self.perf_label.pack(side=LEFT, padx=(10, 0))

    def _create_control_panel(self, parent):
        control_frame = ttk.LabelFrame(parent, text="Controls", padding="10")
        control_frame.pack(fill=X, pady=(0, 10))
        
        row1 = ttk.Frame(control_frame)
        row1.pack(fill=X, pady=(0, 10))
        
        self.start_btn = ttk.Button(
            row1, 
            text='▶ Start Monitoring', 
            command=self.start_monitor,
            bootstyle="success"
        )
        self.start_btn.pack(side=LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(
            row1, 
            text='⏸ Stop Monitoring', 
            command=self.stop_monitor, 
            state=DISABLED,
            bootstyle="danger"
        )
        self.stop_btn.pack(side=LEFT, padx=5)
        
        separator = ttk.Separator(row1, orient='vertical')
        separator.pack(side=LEFT, fill='y', padx=10)
        
        self.add_btn = ttk.Button(
            row1, 
            text='➕ Add IP', 
            command=self.add_ip,
            bootstyle="info"
        )
        self.add_btn.pack(side=LEFT, padx=5)
        
        self.remove_btn = ttk.Button(
            row1, 
            text='➖ Remove Selected IPs', 
            command=self.remove_ip,
            bootstyle="warning"
        )
        self.remove_btn.pack(side=LEFT, padx=5)
        
        self.clear_btn = ttk.Button(
            row1, 
            text='🗑 Clear IP List', 
            command=self.clear_ip_list,
            bootstyle="danger"
        )
        self.clear_btn.pack(side=LEFT, padx=5)
        
        self.import_btn = ttk.Button(
            row1, 
            text='📁 Import IPs', 
            command=self.import_ips,
            bootstyle="secondary"
        )
        self.import_btn.pack(side=LEFT, padx=5)
        
        self.select_all_btn = ttk.Button(
            row1, 
            text='✔ Select All', 
            command=self.select_all,
            bootstyle="info-outline"
        )
        self.select_all_btn.pack(side=LEFT, padx=5)
        
        self.unselect_all_btn = ttk.Button(
            row1, 
            text='✘ Unselect All', 
            command=self.unselect_all,
            bootstyle="warning-outline"
        )
        self.unselect_all_btn.pack(side=LEFT, padx=5)
        
        row2 = ttk.Frame(control_frame)
        row2.pack(fill=X)
        
        ttk.Label(row2, text='Ping Interval:').pack(side=LEFT, padx=(0, 5))
        self.interval_var = tk.StringVar(value='1000')
        self.interval_combo = ttk.Combobox(
            row2, 
            textvariable=self.interval_var, 
            values=['500', '1000', '2000', '5000', '10000'],
            width=8,
            state='readonly'
        )
        self.interval_combo.pack(side=LEFT, padx=5)
        ttk.Label(row2, text='ms').pack(side=LEFT, padx=(0, 10))
        
        ttk.Label(row2, text='UI Update:').pack(side=LEFT, padx=(10, 5))
        self.update_rate_var = tk.StringVar(value='1000')
        self.update_rate_combo = ttk.Combobox(
            row2, 
            textvariable=self.update_rate_var, 
            values=['500', '1000', '2000', '5000'],
            width=6,
            state='readonly'
        )
        self.update_rate_combo.pack(side=LEFT, padx=5)
        self.update_rate_combo.bind('<<ComboboxSelected>>', self.on_update_rate_change)
        ttk.Label(row2, text='ms').pack(side=LEFT, padx=(0, 10))
        
        def keep_dropdown_open(event, combo):
            combo.focus_set()
        self.interval_combo.bind('<Button-1>', lambda event: keep_dropdown_open(event, self.interval_combo))
        self.update_rate_combo.bind('<Button-1>', lambda event: keep_dropdown_open(event, self.update_rate_combo))
        
        self.export_btn = ttk.Button(
            row2, 
            text='💾 Export CSV', 
            command=self.export_csv,
            bootstyle="success-outline"
        )
        self.export_btn.pack(side=LEFT, padx=5)
        
        self.open_folder_btn = ttk.Button(
            row2, 
            text='📂 Open Export Folder', 
            command=self.open_export_folder,
            bootstyle="info-outline"
        )
        self.open_folder_btn.pack(side=LEFT, padx=5)
        
        self._create_theme_menu(row2)

    def _create_theme_menu(self, parent):
        self.theme_var = tk.StringVar(value=self.current_theme)
        theme_menu = ttk.Menubutton(parent, text="🎨 Theme", direction='below')
        theme_menu.pack(side=RIGHT, padx=5)
        
        theme_menu.menu = tk.Menu(theme_menu, tearoff=0)
        theme_menu['menu'] = theme_menu.menu
        
        themes = self.style.theme_names()
        
        dark_themes = ['superhero', 'darkly', 'cyborg', 'vapor', 'solar']
        light_themes = ['cosmo', 'flatly', 'litera', 'minty', 'morph', 'pulse', 'sandstone', 'united', 'yeti']
        colorful_themes = ['cerulean', 'journal', 'lumen', 'lux', 'materia', 'simplex', 'sketchy', 'spacelab']
        
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Dark Themes", state="disabled")
        for theme in dark_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )
        
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Light Themes", state="disabled")
        for theme in light_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )
        
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Colorful Themes", state="disabled")
        for theme in colorful_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )

    def _create_table(self, parent):
        table_frame = ttk.LabelFrame(parent, text="Ping Statistics", padding="10")
        table_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        self.columns = ('select', 'no', 'ip', 'success', 'failure', 'total', 'disconnected', 'last_ping', 'status')
        self.column_configs = {
            'select': {'text': 'Select', 'width': 60, 'anchor': tk.CENTER},
            'no': {'text': 'No.', 'width': 50, 'anchor': tk.CENTER},
            'ip': {'text': 'IP Address', 'width': 150, 'anchor': tk.W},
            'success': {'text': 'Success %', 'width': 80, 'anchor': tk.CENTER},
            'failure': {'text': 'Failure %', 'width': 80, 'anchor': tk.CENTER},
            'total': {'text': 'Total Pings', 'width': 80, 'anchor': tk.CENTER},
            'disconnected': {'text': 'Disconnected (s)', 'width': 120, 'anchor': tk.CENTER},
            'last_ping': {'text': 'Last Ping', 'width': 150, 'anchor': tk.CENTER},
            'status': {'text': 'Status', 'width': 100, 'anchor': tk.CENTER},
        }
        
        self.table = ttk.Treeview(
            master=table_frame,
            columns=self.columns,
            show='headings',
            height=15
        )
        
        for col in self.columns:
            self.table.heading(col, text=self.column_configs[col]['text'], anchor=self.column_configs[col].get('anchor', tk.W))
            self.table.column(col, width=self.column_configs[col]['width'], anchor=self.column_configs[col].get('anchor', tk.W))
        
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill='y')
        
        self.table.bind('<ButtonRelease-1>', self.handle_click)

    def _create_status_bar(self, parent):
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=X, pady=(5, 0))
        
        self.status_var = tk.StringVar(value='Ready - Backend not connected')
        self.status_label = ttk.Label(
            status_frame, 
            textvariable=self.status_var,
            font=('Segoe UI', 9)
        )
        self.status_label.pack(side=LEFT, fill=X, expand=YES)
        
        self.count_var = tk.StringVar(value='IPs: 0 | Active: 0 | Failed: 0')
        self.count_label = ttk.Label(
            status_frame, 
            textvariable=self.count_var,
            font=('Segoe UI', 9)
        )
        self.count_label.pack(side=RIGHT)

    def _start_update_scheduler(self):
        def update_scheduler():
            while True:
                try:
                    self.root.after(0, self.update_performance_metrics)
                    
                    current_time = time.time() * 1000
                    if (current_time - self.last_table_update >= self.update_interval and 
                        self.stats_buffer):
                        self.root.after(0, self.process_batch_updates)
                        self.last_table_update = current_time
                        
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Update scheduler error: {e}")
                    time.sleep(1)
        
        scheduler_thread = threading.Thread(target=update_scheduler, daemon=True)
        scheduler_thread.start()

    def on_update_rate_change(self, event=None):
        try:
            self.update_interval = int(self.update_rate_var.get())
            self.status_var.set(f'UI update rate changed to {self.update_interval}ms')
        except ValueError:
            self.update_interval = 1000
            self.update_rate_var.set('1000')

    def update_performance_metrics(self):
        current_time = time.time()
        time_diff = current_time - self.last_message_time
        
        if time_diff >= 1.0:
            msg_rate = self.message_count / time_diff if time_diff > 0 else 0
            self.perf_label.config(text=f"({msg_rate:.1f} msg/s)")
            self.message_count = 0
            self.last_message_time = current_time

    def change_theme(self, theme_name):
        try:
            self.style.theme_use(theme_name)
            self.current_theme = theme_name
            self.status_var.set(f'Theme changed to: {theme_name.title()}')
        except Exception as e:
            messagebox.showerror("Theme Error", f"Failed to change theme: {e}")

    def open_export_folder(self):
        try:
            export_path = os.getcwd()
            csv_file = os.path.join(export_path, "ping_stats_export.csv")
            if not os.path.exists(csv_file):
                response = messagebox.askyesno(
                    "Export File Not Found", 
                    f"Export file not found at:\n{csv_file}\n\nDo you want to open the current directory anyway?"
                )
                if not response:
                    return
            
            if platform.system() == "Windows":
                os.startfile(export_path)
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", export_path])
            else:
                subprocess.run(["open", export_path])
                
            self.status_var.set(f"Opened export folder: {export_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open export folder: {e}")

    def connect_backend(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((BACKEND_HOST, BACKEND_PORT))
            self.sock.settimeout(None)
            
            self.running = True
            self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
            self.recv_thread.start()
            self.update_connection_status(True)
            
            self.message_count = 0
            self.last_message_time = time.time()
            
        except Exception as e:
            self.update_connection_status(False)
            raise e

    def update_connection_status(self, connected):
        if connected:
            self.connection_indicator.config(foreground="green")
            self.connection_label.config(text="Connected")
            self.status_var.set('Connected to backend')
        else:
            self.connection_indicator.config(foreground="red")
            self.connection_label.config(text="Disconnected")
            self.status_var.set('Backend disconnected')

    def recv_loop(self):
        buffer = ''
        while self.running:
            try:
                data = self.sock.recv(8192)
                if not data:
                    break
                    
                buffer += data.decode('utf-8')
                
                messages = []
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        messages.append(line.strip())
                        print(f"Received: {line.strip()}")
                        
                if messages:
                    self.process_messages_batch(messages)
                    
            except Exception as e:
                self.root.after(0, self.status_var.set, f'Connection error: {e}')
                break
                
        self.root.after(0, self.update_connection_status, False)
        self.running = False

    def process_messages_batch(self, messages):
        for msg in messages:
            try:
                stat = json.loads(msg)
                ip = stat['ip']
                self.stats_buffer[ip] = stat
                self.message_count += 1
            except Exception:
                continue

    def process_batch_updates(self):
        if not self.stats_buffer:
            return
            
        self.ip_stats.update(self.stats_buffer)
        self.stats_buffer.clear()
        self.update_table()

    def toggle_checkbox(self, event, item, ip):
        try:
            self.selected_ips[ip] = not self.selected_ips.get(ip, False)
            self.update_table()
        except Exception as e:
            print(f"Toggle checkbox error: {e}")

    def handle_click(self, event):
        try:
            item = self.table.identify_row(event.y)
            if not item:
                return
            
            column = self.table.identify_column(event.x)
            values = self.table.item(item, 'values')
            ip = values[2]
            
            if column == '#1':
                self.toggle_checkbox(event, item, ip)
            else:
                self.table.selection_set(item)
        except Exception:
            pass

    def select_all(self):
        for ip in self.ip_list:
            self.selected_ips[ip] = True
        self.update_table()
        self.status_var.set('Selected all IPs')

    def unselect_all(self):
        for ip in self.ip_list:
            self.selected_ips[ip] = False
        self.update_table()
        self.status_var.set('Unselected all IPs')

    def update_table(self):
        try:
            scroll_pos = self.table.yview()[0]
            
            for item in self.table.get_children():
                self.table.delete(item)
            
            rows = []
            failed_count = 0
            
            for idx, (ip, stat) in enumerate(self.ip_stats.items(), 1):
                total = stat['pass'] + stat['fail']
                if total > 0:
                    percent_pass = f"{(stat['pass']*100/total):.1f}%"
                    percent_fail = f"{(stat['fail']*100/total):.1f}%"
                    fail_rate = (stat['fail']*100/total)
                    
                    if fail_rate > 50:
                        status = "🔴 Critical"
                        failed_count += 1
                    elif fail_rate > 20:
                        status = "🟡 Warning"
                    elif fail_rate > 0:
                        status = "🟢 Good"
                    else:
                        status = "✅ Perfect"
                else:
                    percent_pass = percent_fail = 'N/A'
                    status = "⚪ No Data"
                
                disconnected = f"{stat['disconnected_time']/1000:.1f}"
                last_ping = datetime.fromtimestamp(stat['last_ping_time']).strftime('%Y-%m-%d %H:%M:%S') if stat['last_ping_time'] else 'N/A'
                checkbox = '☑' if self.selected_ips.get(ip, False) else '☐'
                row = (checkbox, idx, ip, percent_pass, percent_fail, total, disconnected, last_ping, status)
                rows.append(row)
            
            for ip in self.ip_list:
                if ip not in self.ip_stats:
                    idx = len(rows) + 1
                    checkbox = '☑' if self.selected_ips.get(ip, False) else '☐'
                    rows.append((checkbox, idx, ip, 'N/A', 'N/A', 0, '0.0', 'N/A', '⚪ Waiting'))
            
            rows.sort(key=lambda x: x[2])
            rows = [(row[0], i+1, *row[2:]) for i, row in enumerate(rows)]
            
            for row in rows:
                self.table.insert('', 'end', values=row)
            
            self.table.yview_moveto(scroll_pos)
            
            active_count = len(self.ip_stats)
            total_count = len(self.ip_list)
            self.count_var.set(f'IPs: {total_count} | Active: {active_count} | Failed: {failed_count}')
            
        except Exception as e:
            print(f"Table update error: {e}")

    def start_monitor(self):
        if not self.ip_list:
            messagebox.showwarning('Warning', 'Please add some IPs first!')
            return
            
        ping_ips = [ip for ip in self.ip_list if self.selected_ips.get(ip, False)]
        if not ping_ips:
            messagebox.showwarning('Warning', 'Please select at least one IP to ping!')
            return
            
        if not self.running:
            try:
                self.connect_backend()
            except Exception as e:
                messagebox.showerror('Error', f'Cannot connect to backend: {e}')
                return
        
        self.ip_stats.clear()
        self.stats_buffer.clear()
        self.update_table()
        
        self.ip_list = list(set(self.ip_list))
        
        try:
            interval = int(self.interval_var.get())
        except ValueError:
            interval = 1000
            self.interval_var.set('1000')
        
        self.interval = interval
        
        msg = json.dumps({
            'cmd': 'start',
            'ips': ping_ips,
            'interval': self.interval
        }) + '\n'
        
        try:
            self.sock.sendall(msg.encode('utf-8'))
            self.start_btn.config(state=DISABLED)
            self.stop_btn.config(state=NORMAL)
            self.status_var.set(f'Monitoring {len(ping_ips)} IPs...')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to send start command: {e}')

    def stop_monitor(self):
        """Send stop command to backend, keep GUI and backend running."""
        if self.running and self.sock:
            try:
                msg = json.dumps({'cmd': 'stop'}) + '\n'
                self.sock.sendall(msg.encode('utf-8'))
            except Exception as e:
                print(f"Error stopping monitor: {e}")
        
        self.start_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.status_var.set('Monitoring stopped')

    def import_ips(self):
        path = filedialog.askopenfilename(
            title='Import IP List',
            filetypes=[('Text Files', '*.txt'), ('All Files', '*.*')]
        )
        if not path:
            return
        
        try:
            with open(path, 'r') as f:
                imported_count = 0
                for line in f:
                    ip = line.strip()
                    if ip and ip not in self.ip_list:
                        self.ip_list.append(ip)
                        self.selected_ips[ip] = True
                        imported_count += 1
            
            self.status_var.set(f'Imported {imported_count} new IPs. Total: {len(self.ip_list)}')
            self.update_table()
        except Exception as e:
            messagebox.showerror('Error', f'Failed to import IPs: {e}')

    def export_csv(self):
        if not self.running or not self.sock:
            messagebox.showwarning('Warning', 'Backend not connected!')
            return
            
        try:
            msg = json.dumps({'cmd': 'export'}) + '\n'
            self.sock.sendall(msg.encode('utf-8'))
            messagebox.showinfo(
                'Export Started', 
                'Export command sent to backend.\nFile will be saved as "ping_stats_export.csv"\n\nClick "Open Export Folder" to view the file.'
            )
        except Exception as e:
            messagebox.showerror('Error', f'Failed to send export command: {e}')

    def add_ip(self):
        ip = simpledialog.askstring('Add IP', 'Enter IP address:')
        if ip and ip.strip():
            ip = ip.strip()
            if ip not in self.ip_list:
                self.ip_list.append(ip)
                self.selected_ips[ip] = True
                self.status_var.set(f'Added {ip}. Total: {len(self.ip_list)}')
                self.update_table()
            else:
                messagebox.showinfo('Info', f'IP {ip} already exists in the list!')

    def remove_ip(self):
        try:
            selected_ips = [ip for ip, selected in self.selected_ips.items() if selected]
            if not selected_ips:
                messagebox.showinfo('Info', 'Please select at least one IP to remove!')
                return
            
            for ip in selected_ips:
                if ip in self.ip_list:
                    self.ip_list.remove(ip)
                    self.ip_stats.pop(ip, None)
                    self.stats_buffer.pop(ip, None)
                    self.selected_ips.pop(ip, None)
            
            self.status_var.set(f'Removed {len(selected_ips)} IPs. Total: {len(self.ip_list)}')
            self.update_table()
        except Exception as e:
            messagebox.showerror('Error', f'Failed to remove IPs: {e}')

    def clear_ip_list(self):
        if not self.ip_list:
            messagebox.showinfo('Info', 'IP list is already empty!')
            return
            
        response = messagebox.askyesno('Confirm', 'Clear all IPs from the list?')
        if response:
            self.ip_list.clear()
            self.ip_stats.clear()
            self.stats_buffer.clear()
            self.selected_ips.clear()
            self.status_var.set('Cleared all IPs')
            self.update_table()

    def on_close(self):
        """Stop monitoring, terminate backend, and close GUI."""
        self.stop_monitor()
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        if self.backend_process and self.backend_process.poll() is None:
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=2)
            except:
                try:
                    self.backend_process.kill()
                except:
                    pass
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = PingGUI(root)
    root.mainloop()