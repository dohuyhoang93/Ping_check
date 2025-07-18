import socket
import threading
import json
import tkinter as tk
from tkinter import LEFT, RIGHT, X, BOTH, YES, NORMAL, DISABLED, TOP, BOTTOM
from tkinter import ttk
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from ttkbootstrap.tableview import Tableview
from tkinter import filedialog, messagebox, simpledialog
import os
import sys
import subprocess
import platform
import time
from collections import deque
import queue

BACKEND_HOST = '127.0.0.1'
BACKEND_PORT = 7878

class PingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Multi-IP Ping Monitor')
        self.root.geometry('1000x700')
        self.root.minsize(800, 600)
        
        # Initialize with a modern theme
        self.style = Style('superhero')
        self.current_theme = 'superhero'
        
        self.sock = None
        self.recv_thread = None
        self.running = False
        self.ip_stats = {}
        self.interval = 1000
        
        # Optimization: Batch updates và rate limiting
        self.update_queue = queue.Queue()
        self.last_table_update = 0
        self.update_interval = 1000  # Update table mỗi 1 giây
        self.stats_buffer = {}
        self.update_pending = False
        
        # Performance tracking
        self.message_count = 0
        self.last_message_time = time.time()
        
        self._build_ui()
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        
        # Start update scheduler
        self._start_update_scheduler()

    def _build_ui(self):
        # Create main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=YES)

        # Header with title and status
        self._create_header(main_frame)
        
        # Control panel
        self._create_control_panel(main_frame)
        
        # Table with improved styling
        self._create_table(main_frame)
        
        # Status bar
        self._create_status_bar(main_frame)

        # IP list
        self.ip_list = []

    def _create_header(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=X, pady=(0, 15))
        
        # Title
        title_label = ttk.Label(
            header_frame, 
            text="Multi-IP Ping Monitor", 
            font=('Segoe UI', 18, 'bold')
        )
        title_label.pack(side=LEFT)
        
        # Connection status indicator
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
        
        # Performance indicator
        self.perf_label = ttk.Label(
            self.connection_frame,
            text="",
            font=('Segoe UI', 8)
        )
        self.perf_label.pack(side=LEFT, padx=(10, 0))

    def _create_control_panel(self, parent):
        # Control panel with modern styling
        control_frame = ttk.LabelFrame(parent, text="Controls", padding="10")
        control_frame.pack(fill=X, pady=(0, 10))
        
        # Row 1: Main controls
        row1 = ttk.Frame(control_frame)
        row1.pack(fill=X, pady=(0, 10))
        
        # Start/Stop buttons with better styling
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
        
        # Separator
        separator = ttk.Separator(row1, orient='vertical')
        separator.pack(side=LEFT, fill='y', padx=10)
        
        # IP Management
        self.add_btn = ttk.Button(
            row1, 
            text='➕ Add IP', 
            command=self.add_ip,
            bootstyle="info"
        )
        self.add_btn.pack(side=LEFT, padx=5)
        
        self.remove_btn = ttk.Button(
            row1, 
            text='➖ Remove IP', 
            command=self.remove_ip,
            bootstyle="warning"
        )
        self.remove_btn.pack(side=LEFT, padx=5)
        
        self.import_btn = ttk.Button(
            row1, 
            text='📁 Import IPs', 
            command=self.import_ips,
            bootstyle="secondary"
        )
        self.import_btn.pack(side=LEFT, padx=5)
        
        # Row 2: Settings and actions
        row2 = ttk.Frame(control_frame)
        row2.pack(fill=X)
        
        # Interval setting
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
        
        # Update rate setting
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
        
        # Export controls
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
        
        # Theme selector
        self._create_theme_menu(row2)

    def _create_theme_menu(self, parent):
        # Theme menu button
        self.theme_var = tk.StringVar(value=self.current_theme)
        theme_menu = ttk.Menubutton(parent, text="🎨 Theme", direction='below')
        theme_menu.pack(side=RIGHT, padx=5)
        
        # Create theme menu
        theme_menu.menu = tk.Menu(theme_menu, tearoff=0)
        theme_menu['menu'] = theme_menu.menu
        
        # Get available themes and organize them
        themes = self.style.theme_names()
        
        # Group themes by type
        dark_themes = ['superhero', 'darkly', 'cyborg', 'vapor', 'solar']
        light_themes = ['cosmo', 'flatly', 'litera', 'minty', 'morph', 'pulse', 'sandstone', 'united', 'yeti']
        colorful_themes = ['cerulean', 'journal', 'lumen', 'lux', 'materia', 'simplex', 'sketchy', 'spacelab']
        
        # Add dark themes
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Dark Themes", state="disabled")
        for theme in dark_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )
        
        # Add light themes
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Light Themes", state="disabled")
        for theme in light_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )
        
        # Add colorful themes
        theme_menu.menu.add_separator()
        theme_menu.menu.add_command(label="Colorful Themes", state="disabled")
        for theme in colorful_themes:
            if theme in themes:
                theme_menu.menu.add_command(
                    label=f"  {theme.title()}", 
                    command=lambda t=theme: self.change_theme(t)
                )

    def _create_table(self, parent):
        # Table frame with better styling
        table_frame = ttk.LabelFrame(parent, text="Ping Statistics", padding="10")
        table_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        # Enhanced column configuration
        self.columns = [
            {'text': 'IP Address', 'stretch': True, 'width': 150},
            {'text': 'Success %', 'stretch': False, 'width': 80},
            {'text': 'Failure %', 'stretch': False, 'width': 80},
            {'text': 'Total Pings', 'stretch': False, 'width': 80},
            {'text': 'Disconnected (s)', 'stretch': False, 'width': 120},
            {'text': 'Status', 'stretch': False, 'width': 100},
        ]
        
        self.table = Tableview(
            master=table_frame,
            coldata=self.columns,
            rowdata=[],
            paginated=True,
            pagesize=50,  # Phân trang để tăng performance
            searchable=True,
            autofit=True,
            height=15,
            stripecolor=("#2b2b2b", None)
        )
        self.table.pack(fill=BOTH, expand=YES)
        self.table.bind('<Double-1>', self.on_table_double_click)

    def _create_status_bar(self, parent):
        # Enhanced status bar
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=X, pady=(5, 0))
        
        # Status message
        self.status_var = tk.StringVar(value='Ready - Backend not connected')
        self.status_label = ttk.Label(
            status_frame, 
            textvariable=self.status_var,
            font=('Segoe UI', 9)
        )
        self.status_label.pack(side=LEFT, fill=X, expand=YES)
        
        # Statistics
        self.count_var = tk.StringVar(value='IPs: 0 | Active: 0 | Failed: 0')
        self.count_label = ttk.Label(
            status_frame, 
            textvariable=self.count_var,
            font=('Segoe UI', 9)
        )
        self.count_label.pack(side=RIGHT)

    def _start_update_scheduler(self):
        """Start the update scheduler để batch updates"""
        def update_scheduler():
            while True:
                try:
                    # Update performance metrics
                    self.root.after(0, self.update_performance_metrics)
                    
                    # Check if we need to update table
                    current_time = time.time() * 1000
                    if (current_time - self.last_table_update >= self.update_interval and 
                        self.stats_buffer):
                        self.root.after(0, self.process_batch_updates)
                        self.last_table_update = current_time
                        
                    time.sleep(0.1)  # Check every 100ms
                except Exception as e:
                    print(f"Update scheduler error: {e}")
                    time.sleep(1)
        
        scheduler_thread = threading.Thread(target=update_scheduler, daemon=True)
        scheduler_thread.start()

    def on_update_rate_change(self, event=None):
        """Handle update rate change"""
        try:
            self.update_interval = int(self.update_rate_var.get())
            self.status_var.set(f'UI update rate changed to {self.update_interval}ms')
        except ValueError:
            self.update_interval = 1000
            self.update_rate_var.set('1000')

    def update_performance_metrics(self):
        """Update performance metrics display"""
        current_time = time.time()
        time_diff = current_time - self.last_message_time
        
        if time_diff >= 1.0:  # Update every second
            msg_rate = self.message_count / time_diff if time_diff > 0 else 0
            self.perf_label.config(text=f"({msg_rate:.1f} msg/s)")
            self.message_count = 0
            self.last_message_time = current_time

    def change_theme(self, theme_name):
        """Change the application theme"""
        try:
            self.style.theme_use(theme_name)
            self.current_theme = theme_name
            self.status_var.set(f'Theme changed to: {theme_name.title()}')
        except Exception as e:
            messagebox.showerror("Theme Error", f"Failed to change theme: {e}")

    def open_export_folder(self):
        """Open the folder containing exported CSV files"""
        try:
            # Get the directory where the backend is likely running
            export_path = os.getcwd()  # Current working directory
            
            # Check if export file exists
            csv_file = os.path.join(export_path, "ping_stats_export.csv")
            if not os.path.exists(csv_file):
                response = messagebox.askyesno(
                    "Export File Not Found", 
                    f"Export file not found at:\n{csv_file}\n\nDo you want to open the current directory anyway?"
                )
                if not response:
                    return
            
            # Open file explorer based on OS
            if platform.system() == "Windows":
                os.startfile(export_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", export_path])
            else:  # Linux
                subprocess.run(["xdg-open", export_path])
                
            self.status_var.set(f"Opened export folder: {export_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open export folder: {e}")

    def connect_backend(self):
        """Connect to backend with improved error handling"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)  # 10 second timeout
            self.sock.connect((BACKEND_HOST, BACKEND_PORT))
            self.sock.settimeout(None)  # Remove timeout after connection
            
            self.running = True
            self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
            self.recv_thread.start()
            self.update_connection_status(True)
            
            # Reset performance counters
            self.message_count = 0
            self.last_message_time = time.time()
            
        except Exception as e:
            self.update_connection_status(False)
            raise e

    def update_connection_status(self, connected):
        """Update the connection status indicator"""
        if connected:
            self.connection_indicator.config(foreground="green")
            self.connection_label.config(text="Connected")
            self.status_var.set('Connected to backend')
        else:
            self.connection_indicator.config(foreground="red")
            self.connection_label.config(text="Disconnected")
            self.status_var.set('Backend disconnected')

    def recv_loop(self):
        """Optimized receive loop with buffering"""
        buffer = ''
        while self.running:
            try:
                data = self.sock.recv(8192)  # Increased buffer size
                if not data:
                    break
                    
                buffer += data.decode('utf-8')
                
                # Process multiple messages in batch
                messages = []
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        messages.append(line.strip())
                
                # Process messages in batch
                if messages:
                    self.process_messages_batch(messages)
                    
            except Exception as e:
                self.root.after(0, self.status_var.set, f'Connection error: {e}')
                break
                
        self.root.after(0, self.update_connection_status, False)
        self.running = False

    def process_messages_batch(self, messages):
        """Process multiple messages in batch"""
        for msg in messages:
            try:
                stat = json.loads(msg)
                ip = stat['ip']
                # Buffer the update instead of immediately updating
                self.stats_buffer[ip] = stat
                self.message_count += 1
            except Exception:
                continue

    def process_batch_updates(self):
        """Process buffered updates in batch"""
        if not self.stats_buffer:
            return
            
        # Update ip_stats with buffered data
        self.ip_stats.update(self.stats_buffer)
        
        # Clear buffer
        self.stats_buffer.clear()
        
        # Update table
        self.update_table()

    def update_table(self):
        """Optimized table update"""
        try:
            rows = []
            failed_count = 0
            
            for ip, stat in self.ip_stats.items():
                total = stat['pass'] + stat['fail']
                if total > 0:
                    percent_pass = f"{(stat['pass']*100/total):.1f}%"
                    percent_fail = f"{(stat['fail']*100/total):.1f}%"
                    fail_rate = (stat['fail']*100/total)
                    
                    # Determine status
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
                
                disconnected = f"{stat['disconnected_time']//1000}"
                row = (ip, percent_pass, percent_fail, total, disconnected, status)
                rows.append(row)
            
            # Add IPs that haven't been pinged yet
            for ip in self.ip_list:
                if ip not in self.ip_stats:
                    rows.append((ip, 'N/A', 'N/A', 0, '0', '⚪ Waiting'))
            
            # Sort rows by IP for consistent display
            rows.sort(key=lambda x: x[0])
            
            # Update table data efficiently
            self.table.build_table_data(coldata=self.columns, rowdata=rows)
            
            # Update status panel
            active_count = len(self.ip_stats)
            total_count = len(self.ip_list)
            self.count_var.set(f'IPs: {total_count} | Active: {active_count} | Failed: {failed_count}')
            
        except Exception as e:
            print(f"Table update error: {e}")

    def start_monitor(self):
        if not self.ip_list:
            messagebox.showwarning('Warning', 'Please add some IPs first!')
            return
            
        if not self.running:
            try:
                self.connect_backend()
            except Exception as e:
                messagebox.showerror('Error', f'Cannot connect to backend: {e}')
                return
        
        # Clear existing stats
        self.ip_stats.clear()
        self.stats_buffer.clear()
        self.update_table()
        
        # Remove duplicates
        self.ip_list = list(set(self.ip_list))
        
        # Get interval
        try:
            interval = int(self.interval_var.get())
        except ValueError:
            interval = 1000
            self.interval_var.set('1000')
        
        self.interval = interval
        
        # Send start command
        msg = json.dumps({
            'cmd': 'start',
            'ips': self.ip_list,
            'interval': self.interval
        }) + '\n'
        
        try:
            self.sock.sendall(msg.encode('utf-8'))
            self.start_btn.config(state=DISABLED)
            self.stop_btn.config(state=NORMAL)
            self.status_var.set(f'Monitoring {len(self.ip_list)} IPs...')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to send start command: {e}')

    def stop_monitor(self):
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
                self.status_var.set(f'Added {ip}. Total: {len(self.ip_list)}')
                self.update_table()
            else:
                messagebox.showinfo('Info', f'IP {ip} already exists in the list!')

    def remove_ip(self):
        try:
            selected = self.table.get_selected_row()
            if selected:
                ip = selected[0]
                if ip in self.ip_list:
                    self.ip_list.remove(ip)
                    self.ip_stats.pop(ip, None)
                    self.stats_buffer.pop(ip, None)
                    self.status_var.set(f'Removed {ip}. Total: {len(self.ip_list)}')
                    self.update_table()
                else:
                    messagebox.showinfo('Info', f'IP {ip} not found in the list!')
            else:
                messagebox.showinfo('Info', 'Please select an IP to remove!')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to remove IP: {e}')

    def on_table_double_click(self, event):
        self.remove_ip()

    def on_close(self):
        self.stop_monitor()
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = PingGUI(root)
    root.mainloop()
