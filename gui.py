import socket
import threading
import json
import tkinter as tk
from tkinter import LEFT, RIGHT, X, BOTH, YES, NORMAL, DISABLED
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from ttkbootstrap.tableview import Tableview
from tkinter import filedialog, messagebox, simpledialog

BACKEND_HOST = '127.0.0.1'
BACKEND_PORT = 7878

class PingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Multi-IP Ping Monitor')
        self.style = Style('cosmo')
        self.sock = None
        self.recv_thread = None
        self.running = False
        self.ip_stats = {}
        self.interval = 1000
        self._build_ui()
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=X, padx=5, pady=5)
        self.start_btn = tk.Button(toolbar, text='Start', command=self.start_monitor)
        self.start_btn.pack(side=LEFT, padx=2)
        self.stop_btn = tk.Button(toolbar, text='Stop', command=self.stop_monitor, state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=2)
        self.import_btn = tk.Button(toolbar, text='Import IPs', command=self.import_ips)
        self.import_btn.pack(side=LEFT, padx=2)
        self.add_btn = tk.Button(toolbar, text='Add IP', command=self.add_ip)
        self.add_btn.pack(side=LEFT, padx=2)
        self.remove_btn = tk.Button(toolbar, text='Remove IP', command=self.remove_ip)
        self.remove_btn.pack(side=LEFT, padx=2)
        self.export_btn = tk.Button(toolbar, text='Export CSV', command=self.export_csv)
        self.export_btn.pack(side=LEFT, padx=2)
        tk.Label(toolbar, text='Interval (ms):').pack(side=LEFT, padx=2)
        self.interval_var = tk.StringVar(value='1000')
        self.interval_entry = tk.Entry(toolbar, textvariable=self.interval_var, width=6)
        self.interval_entry.pack(side=LEFT, padx=2)
        self.theme_btn = tk.Button(toolbar, text='Switch Theme', command=self.switch_theme)
        self.theme_btn.pack(side=LEFT, padx=2)

        # Table
        self.columns = [
            {'text': 'IP', 'stretch': True},
            {'text': '% Pass', 'stretch': False},
            {'text': '% Fail', 'stretch': False},
            {'text': 'Total', 'stretch': False},
            {'text': 'Disconnected (s)', 'stretch': False},
        ]
        self.table = Tableview(
            master=self.root,
            coldata=self.columns,
            rowdata=[],
            paginated=False,
            searchable=False,
            autofit=True,
            height=15
        )
        self.table.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        self.table.bind('<Double-1>', self.on_table_double_click)

        # Status bar
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill=X, padx=5, pady=2)
        self.status_var = tk.StringVar(value='Disconnected')
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, anchor='w')
        self.status_label.pack(side=LEFT, fill=X, expand=YES)
        self.count_var = tk.StringVar(value='IPs: 0 | Threads: 0')
        self.count_label = tk.Label(status_frame, textvariable=self.count_var, anchor='e')
        self.count_label.pack(side=RIGHT)

        # IP list
        self.ip_list = []

    def connect_backend(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((BACKEND_HOST, BACKEND_PORT))
        self.running = True
        self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
        self.recv_thread.start()
        self.status_var.set('Connected')

    def recv_loop(self):
        buffer = ''
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self.root.after(0, self.handle_backend_msg, line.strip())
            except Exception as e:
                self.root.after(0, self.status_var.set, f'Error: {e}')
                break
        self.root.after(0, self.status_var.set, 'Disconnected')
        self.running = False

    def handle_backend_msg(self, msg):
        try:
            stat = json.loads(msg)
            ip = stat['ip']
            self.ip_stats[ip] = stat
            self.update_table()
        except Exception:
            pass

    def update_table(self):
        rows = []
        for ip, stat in self.ip_stats.items():
            total = stat['pass'] + stat['fail']
            percent_pass = f"{(stat['pass']*100/total):.1f}%" if total > 0 else 'N/A'
            percent_fail = f"{(stat['fail']*100/total):.1f}%" if total > 0 else 'N/A'
            disconnected = f"{stat['disconnected_time']//1000}"
            row = (ip, percent_pass, percent_fail, total, disconnected)
            rows.append(row)
        
        # Add IPs that haven't been pinged yet
        for ip in self.ip_list:
            if ip not in self.ip_stats:
                rows.append((ip, 'N/A', 'N/A', 0, '0'))
        
        # Update table data
        self.table.build_table_data(coldata=self.columns, rowdata=rows)
        
        # Update status panel
        self.count_var.set(f'IPs: {len(self.ip_list)} | Active: {len(self.ip_stats)}')

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
            self.status_var.set('Monitoring...')
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
        self.status_var.set('Stopped')

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
            messagebox.showinfo('Export', 'Export command sent to backend. File will be saved as ping_stats_export.csv')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to send export command: {e}')

    def switch_theme(self):
        themes = self.style.theme_names()
        current = self.style.theme.name
        try:
            idx = themes.index(current)
            next_theme = themes[(idx + 1) % len(themes)]
            self.style.theme_use(next_theme)
            self.status_var.set(f'Theme changed to: {next_theme}')
        except Exception as e:
            print(f"Error switching theme: {e}")

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
